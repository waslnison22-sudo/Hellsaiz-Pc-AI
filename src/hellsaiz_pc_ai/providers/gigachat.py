from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class GigaChatProviderError(RuntimeError):
    pass


class GigaChatProvider:
    """Native GigaChat REST adapter with OAuth refresh and native function-call mapping."""

    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    DEFAULT_BASE_URL = "https://api.giga.chat/v1"
    ALLOWED_SCOPES = {"GIGACHAT_API_PERS", "GIGACHAT_API_B2B", "GIGACHAT_API_CORP"}

    def __init__(
        self,
        authorization_key: str,
        model: str = "GigaChat",
        *,
        base_url: str = DEFAULT_BASE_URL,
        scope: str = "GIGACHAT_API_PERS",
        timeout_seconds: int = 60,
        urlopen_func: Callable[..., Any] = urlopen,
    ) -> None:
        key = authorization_key.strip()
        if key.lower().startswith("basic "):
            key = key[6:].strip()
        if not key or len(key) > 8192 or any(ord(char) < 32 for char in key):
            raise ValueError("Укажи корректный ключ авторизации GigaChat.")
        parsed = urlparse(base_url.rstrip("/"))
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.giga.chat"
            or parsed.path.rstrip("/") not in {"", "/v1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("GigaChat должен использовать официальный HTTPS адрес https://api.giga.chat/v1.")
        if scope not in self.ALLOWED_SCOPES:
            raise ValueError("Недопустимый scope GigaChat API.")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 5 <= timeout_seconds <= 600:
            raise ValueError("Тайм-аут GigaChat должен быть от 5 до 600 секунд.")
        if not isinstance(model, str) or not 1 <= len(model.strip()) <= 128:
            raise ValueError("Укажи корректное имя модели GigaChat.")
        self._authorization_key = key
        self.base_url = self.DEFAULT_BASE_URL
        self.model = model.strip()
        self.scope = scope
        self.timeout_seconds = timeout_seconds
        self._urlopen = urlopen_func
        self._token = ""
        self._token_expires_at = 0.0
        self._token_lock = threading.Lock()

    def _read_json(self, request: Request, *, max_bytes: int = 8 * 1024 * 1024) -> dict[str, Any]:
        try:
            response = self._urlopen(request, timeout=self.timeout_seconds)
            with response:
                raw = response.read(max_bytes + 1)
        except HTTPError as exc:
            try:
                detail = exc.read(2048).decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            detail = detail.replace(self._authorization_key, "[скрыто]")
            raise GigaChatProviderError(
                f"GigaChat API вернул HTTP {exc.code}" + (f": {detail}" if detail else ".")
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise GigaChatProviderError(
                f"Не удалось подключиться к GigaChat API: {type(exc).__name__}."
            ) from exc
        if len(raw) > max_bytes:
            raise GigaChatProviderError("GigaChat API вернул ответ превышающий допустимый размер.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise GigaChatProviderError("GigaChat API вернул некорректный JSON/UTF-8.") from exc
        if not isinstance(payload, dict):
            raise GigaChatProviderError("GigaChat API вернул ответ неожиданного формата.")
        return payload

    def _get_access_token(self, *, force_refresh: bool = False) -> str:
        with self._token_lock:
            now = time.time()
            if not force_refresh and self._token and now < self._token_expires_at:
                return self._token
            request = Request(
                self.OAUTH_URL,
                data=urlencode({"scope": self.scope}).encode("ascii"),
                headers={
                    "Authorization": f"Basic {self._authorization_key}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "RqUID": str(uuid.uuid4()),
                },
                method="POST",
            )
            payload = self._read_json(request, max_bytes=256 * 1024)
            token = payload.get("access_token")
            expires_at = payload.get("expires_at")
            if not isinstance(token, str) or not token.strip():
                raise GigaChatProviderError("GigaChat не вернул access_token.")
            if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
                raise GigaChatProviderError("GigaChat не вернул корректный срок действия токена.")
            expiry = float(expires_at)
            if expiry > 10_000_000_000:
                expiry /= 1000.0
            if expiry <= now:
                raise GigaChatProviderError("GigaChat вернул уже истёкший токен доступа.")
            self._token = token.strip()
            self._token_expires_at = expiry - 30.0
            return self._token

    @staticmethod
    def _function_definitions(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        functions = []
        for tool in tools:
            if not isinstance(tool, dict) or tool.get("type") != "function":
                continue
            function = tool.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not isinstance(name, str) or not name:
                continue
            definition = {
                "name": name,
                "description": str(function.get("description") or ""),
                "parameters": function.get("parameters") or {"type": "object", "properties": {}},
            }
            functions.append(definition)
        return functions

    @staticmethod
    def _map_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mapped: list[dict[str, Any]] = []
        tool_names: dict[str, str] = {}
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role == "tool":
                call_id = str(message.get("tool_call_id") or "")
                function_name = tool_names.get(call_id)
                if not function_name:
                    raise GigaChatProviderError("Не удалось сопоставить результат инструмента с вызовом GigaChat.")
                mapped.append({
                    "role": "function",
                    "name": function_name,
                    "content": str(message.get("content") or "{}"),
                })
                continue
            if role == "assistant" and message.get("tool_calls"):
                calls = message["tool_calls"]
                if not isinstance(calls, list) or len(calls) != 1:
                    raise GigaChatProviderError(
                        "GigaChat v1 обрабатывает один пользовательский вызов функции за ответ."
                    )
                raw_call = calls[0]
                if not isinstance(raw_call, dict) or not isinstance(raw_call.get("function"), dict):
                    raise GigaChatProviderError("История содержит некорректный вызов инструмента.")
                function = raw_call["function"]
                name = function.get("name")
                if not isinstance(name, str) or not name:
                    raise GigaChatProviderError("В истории отсутствует имя вызванной функции.")
                arguments = function.get("arguments", "{}")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError as exc:
                        raise GigaChatProviderError("Аргументы функции в истории повреждены.") from exc
                if not isinstance(arguments, dict):
                    raise GigaChatProviderError("Аргументы функции должны быть JSON-объектом.")
                call_id = str(raw_call.get("id") or uuid.uuid4().hex)
                tool_names[call_id] = name
                mapped_assistant = {
                    "role": "assistant",
                    "content": str(message.get("content") or ""),
                    "function_call": {"name": name, "arguments": arguments},
                }
                if message.get("functions_state_id"):
                    mapped_assistant["functions_state_id"] = message["functions_state_id"]
                mapped.append(mapped_assistant)
                continue
            if role not in {"system", "user", "assistant", "function"}:
                continue
            item = {"role": role, "content": str(message.get("content") or "")}
            if role == "function" and isinstance(message.get("name"), str):
                item["name"] = message["name"]
            if message.get("functions_state_id"):
                item["functions_state_id"] = message["functions_state_id"]
            mapped.append(item)
        return mapped

    def _chat_request(self, payload: dict[str, Any], token: str) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        return self._read_json(request)

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        functions = self._function_definitions(tools)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._map_messages(messages),
            "temperature": 0.3,
        }
        if functions:
            payload["functions"] = functions
            payload["function_call"] = "auto"
        token = self._get_access_token()
        try:
            data = self._chat_request(payload, token)
        except GigaChatProviderError as exc:
            # A 401 is an explicit authentication rejection; refresh once.
            if "HTTP 401" not in str(exc):
                raise
            self._token = ""
            token = self._get_access_token(force_refresh=True)
            data = self._chat_request(payload, token)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GigaChatProviderError("Ответ GigaChat не содержит choices[0].message.") from exc
        if not isinstance(message, dict):
            raise GigaChatProviderError("GigaChat вернул некорректное сообщение.")
        normalized = {
            "role": "assistant",
            "content": str(message.get("content") or ""),
        }
        if message.get("functions_state_id"):
            normalized["functions_state_id"] = message["functions_state_id"]
        function_call = message.get("function_call")
        if function_call is not None:
            if not isinstance(function_call, dict):
                raise GigaChatProviderError("GigaChat вернул некорректный function_call.")
            name = function_call.get("name")
            arguments = function_call.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise GigaChatProviderError("GigaChat вернул повреждённые аргументы функции.") from exc
            if not isinstance(name, str) or not name or not isinstance(arguments, dict):
                raise GigaChatProviderError("GigaChat вернул некорректное имя или аргументы функции.")
            normalized["tool_calls"] = [{
                "id": uuid.uuid4().hex,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }]
        return {"message": normalized}

    def list_models(self) -> list[str]:
        request = Request(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self._get_access_token()}", "Accept": "application/json"},
            method="GET",
        )
        payload = self._read_json(request, max_bytes=2 * 1024 * 1024)
        data = payload.get("data")
        if not isinstance(data, list):
            raise GigaChatProviderError("GigaChat вернул некорректный список моделей.")
        return [
            item["id"]
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]

    def health_check(self) -> dict[str, Any]:
        started = time.monotonic()
        models = self.list_models()
        return {
            "ok": True,
            "provider": "gigachat",
            "model": self.model,
            "model_available": self.model in models,
            "models": models,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "capabilities": {
                "chat_completions": True,
                "function_calling": True,
                "streaming": False,
                "vision": False,
                "json_mode": False,
            },
        }

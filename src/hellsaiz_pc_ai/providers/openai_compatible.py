from __future__ import annotations

import ipaddress
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    pass


def _is_loopback_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


class OpenAICompatibleProvider:
    """Client for a local llama.cpp or other OpenAI-compatible inference server."""

    def __init__(
        self, base_url: str, model: str, api_key: str = "not-needed",
        timeout_seconds: int = 120, allow_remote: bool = False
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 1 <= timeout_seconds <= 600
        ):
            raise ValueError("LLM timeout must be between 1 and 600 seconds.")

        parsed = urlparse(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("LLM endpoint must be a valid HTTP(S) base URL without embedded credentials.")

        local_endpoint = _is_loopback_url(self.base_url)
        if not local_endpoint and not allow_remote:
            raise ValueError("Remote LLM endpoints are blocked; use localhost or explicitly opt in.")
        if not local_endpoint and parsed.scheme != "https":
            raise ValueError("Remote LLM endpoints must use HTTPS to protect credentials.")
        self.timeout_seconds = timeout_seconds

    def list_models(self) -> list[str]:
        request = Request(
            f"{self.base_url}/models",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ProviderError(f"Model discovery failed with HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderError(
                f"Не удалось получить список моделей ({type(exc).__name__})."
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("Сервер моделей вернул некорректный JSON/UTF-8.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ProviderError("Сервер моделей вернул неподдерживаемый формат /models.")
        return [
            item["id"]
            for item in payload["data"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]

    def health_check(self) -> dict[str, Any]:
        models = self.list_models()
        return {
            "ok": True,
            "provider": "openai-compatible",
            "model": self.model,
            "model_available": self.model in models,
            "models": models,
            "capabilities": {
                "chat_completions": True,
                "function_calling": "model-dependent",
                "streaming": "not-probed",
                "vision": "not-probed",
                "json_mode": "not-probed",
            },
        }

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0.3}
        if tools:
            payload.update(tools=tools, tool_choice="auto")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise ProviderError(f"Local model server HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderError(f"Не удалось подключиться к локальной LLM ({self.base_url}): {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("Локальный сервер вернул некорректный JSON/UTF-8.") from exc
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Ответ сервера не соответствует Chat Completions API.") from exc
        if not isinstance(message, dict):
            raise ProviderError("Локальная модель вернула некорректное сообщение.")
        return {"message": message}

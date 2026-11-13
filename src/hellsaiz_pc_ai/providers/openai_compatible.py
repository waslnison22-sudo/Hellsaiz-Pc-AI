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
    if parsed.scheme != "http" or not parsed.hostname:
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
        self.timeout_seconds = timeout_seconds
        if not allow_remote and not _is_loopback_url(self.base_url):
            raise ValueError("Remote LLM endpoints are blocked; use localhost or explicitly opt in.")

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

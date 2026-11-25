"""DeepSeek provider: a local dsh endpoint or the cloud DeepSeek API.

Both modes speak the OpenAI Chat Completions protocol, so one client covers
``http://127.0.0.1:8000/v1`` (dsh) and ``https://api.deepseek.com``. Transient
failures are retried a couple of times; technical details go to the log while
callers receive a human-readable message.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_CLOUD_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
TIMEOUT_SECONDS = 8
RETRY_DELAYS = (0.0, 0.4, 0.8)
MAX_RESPONSE_BYTES = 4 * 1024 * 1024

HUMAN_UNAVAILABLE = (
    "ИИ-провайдер сейчас не отвечает — проверь соединение и попробуй позже."
)
HUMAN_UNAUTHORIZED = "Ключ DeepSeek отклонён — проверь ключ в настройках ИИ-провайдера."
HUMAN_BAD_RESPONSE = "ИИ-провайдер вернул неожиданный ответ — попробуй ещё раз."


class DeepSeekError(RuntimeError):
    """Provider failure carrying a message that is safe to show in the chat."""


def _is_loopback(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.hostname) and parsed.hostname.lower() in {"127.0.0.1", "localhost", "::1"}


class DeepSeekProvider:
    """OpenAI-compatible client for DeepSeek (local endpoint or cloud API)."""

    def __init__(
        self,
        mode: str = "local",
        base_url: str | None = None,
        api_key: str = "",
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = TIMEOUT_SECONDS,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        normalized_mode = str(mode or "local").casefold().strip()
        if normalized_mode not in {"local", "cloud"}:
            raise ValueError("Режим DeepSeek должен быть «local» или «cloud».")
        self.mode = normalized_mode
        resolved = (base_url or "").strip() or (
            DEFAULT_LOCAL_BASE_URL if normalized_mode == "local" else DEFAULT_CLOUD_BASE_URL
        )
        parsed = urlparse(resolved)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Адрес ИИ-провайдера должен быть корректным HTTP(S) URL.")
        if normalized_mode == "cloud":
            if not parsed.scheme == "https":
                raise ValueError("Облачный режим DeepSeek требует HTTPS.")
            if not api_key:
                raise ValueError("Облачный режим DeepSeek требует API-ключ.")
        elif not _is_loopback(resolved):
            raise ValueError("Локальный режим DeepSeek принимает только localhost-адрес.")
        if not 1 <= int(timeout_seconds) <= 120:
            raise ValueError("Таймаут ИИ-провайдера должен быть от 1 до 120 секунд.")
        self.base_url = resolved.rstrip("/")
        self.api_key = api_key or "not-needed"
        self.model = model or DEFAULT_MODEL
        self.timeout_seconds = int(timeout_seconds)
        self._opener = opener
        self._sleep = sleep

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for index, delay in enumerate(RETRY_DELAYS):
            if delay:
                self._sleep(delay)
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    raw = response.read(MAX_RESPONSE_BYTES)
                break
            except HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read(1024).decode("utf-8", errors="replace")
                except Exception:
                    detail = ""
                logging.warning("DeepSeek HTTP %s: %s", exc.code, detail)
                last_error = exc
                if exc.code in {400, 401, 403, 404}:
                    raise DeepSeekError(
                        HUMAN_UNAUTHORIZED if exc.code in {401, 403} else HUMAN_BAD_RESPONSE
                    ) from exc
                continue
            except (URLError, TimeoutError, OSError) as exc:
                logging.warning(
                    "DeepSeek request failed (attempt %d/%d): %s",
                    index + 1,
                    len(RETRY_DELAYS),
                    exc,
                )
                last_error = exc
                continue
        else:
            raise DeepSeekError(HUMAN_UNAVAILABLE) from last_error

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logging.warning("DeepSeek returned non-JSON: %s", exc)
            raise DeepSeekError(HUMAN_BAD_RESPONSE) from exc
        if not isinstance(data, dict):
            raise DeepSeekError(HUMAN_BAD_RESPONSE)
        return data

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
        }
        if tools:
            payload.update(tools=tools, tool_choice="auto")
        data = self._request(payload)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            logging.warning("DeepSeek response without choices: %s", str(data)[:400])
            raise DeepSeekError(HUMAN_BAD_RESPONSE) from exc
        if not isinstance(message, dict):
            raise DeepSeekError(HUMAN_BAD_RESPONSE)
        return {"message": message}

    def check_connection(self) -> str:
        """Human-readable status for the settings button."""
        try:
            self.complete([{"role": "user", "content": "ping"}], [])
        except DeepSeekError as exc:
            return str(exc)
        mode_label = "локальный dsh" if self.mode == "local" else "облако DeepSeek"
        return f"Соединение установлено: {mode_label}, модель {self.model}."

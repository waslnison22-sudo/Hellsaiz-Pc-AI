from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from hellsaiz_pc_ai.core.models import RiskLevel
from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.network.v2raytun import (
    DEFAULT_HEALTH_URL,
    check_http_proxy,
    validate_proxy_url,
)
from hellsaiz_pc_ai.telegram.config import AVAILABLE_SAFE_TOOLS, validate_bot_token


MAX_RESPONSE_BYTES = 1024 * 1024
MAX_MESSAGE_LENGTH = 3500
POLL_TIMEOUT_SECONDS = 20
HTTP_TIMEOUT_SECONDS = 30


class TelegramWorkerError(RuntimeError):
    pass


class TelegramBotWorker(threading.Thread):
    """Single-purpose long-polling bot with explicit user/chat and safe-tool allowlists."""

    COMMAND_TO_TOOL = {
        "/time": "get_local_time",
        "/system": "get_system_info",
        "/reminders": "list_reminders",
    }

    def __init__(
        self,
        token: str,
        registry: ToolRegistry,
        *,
        allowed_user_ids: set[int] | list[int],
        allowed_chat_ids: set[int] | list[int],
        allowed_tools: set[str] | list[str] = (),
        proxy_url: str = "",
        require_proxy: bool = True,
        health_url: str = DEFAULT_HEALTH_URL,
        app_version: str = "unknown",
        status_callback: Callable[[str], None] | None = None,
        api_call: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        network_checker: Callable[[str, str], Any] = check_http_proxy,
        network_retry_seconds: float = 10.0,
    ) -> None:
        super().__init__(name="HellsaizTelegramWorker", daemon=True)
        self.token = validate_bot_token(token)
        self.registry = registry
        self.allowed_user_ids = frozenset(allowed_user_ids)
        self.allowed_chat_ids = frozenset(allowed_chat_ids)
        self.allowed_tools = frozenset(allowed_tools)
        if self.allowed_tools - AVAILABLE_SAFE_TOOLS:
            raise ValueError("Telegram разрешены только безопасные read-only инструменты.")
        if not self.allowed_user_ids or not self.allowed_chat_ids:
            raise ValueError("Для Telegram обязательны разрешённые user ID и chat ID.")
        self.proxy_url = validate_proxy_url(proxy_url) if proxy_url else ""
        self.require_proxy = bool(require_proxy)
        self.health_url = health_url or DEFAULT_HEALTH_URL
        self.app_version = app_version
        self.status_callback = status_callback or (lambda _message: None)
        self._api_call_injected = api_call
        if not 0.0 <= network_retry_seconds <= 300.0:
            raise ValueError("network_retry_seconds должен быть от 0 до 300 секунд.")
        self.network_retry_seconds = network_retry_seconds
        self._network_checker = network_checker
        self._stop_event = threading.Event()
        self._offset: int | None = None
        self._status_lock = threading.Lock()

    def stop(self) -> None:
        self._stop_event.set()

    def _status(self, message: str) -> None:
        try:
            with self._status_lock:
                self.status_callback(message[:500])
        except Exception:
            logging.exception("Telegram status callback failed.")

    def _api_call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._api_call_injected is not None:
            return self._api_call_injected(method, payload)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "HellsaizPC_AI-TelegramWorker/0.1",
            },
            method="POST",
        )
        proxies = {"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else {}
        opener = build_opener(ProxyHandler(proxies))
        try:
            with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            if exc.code == 409:
                raise TelegramWorkerError("HTTP 409: уже запущен другой polling worker или включён webhook.") from exc
            if exc.code == 401:
                raise TelegramWorkerError("HTTP 401: Telegram не принял токен бота.") from exc
            if exc.code == 429:
                raise TelegramWorkerError("HTTP 429: Telegram ограничил частоту запросов.") from exc
            raise TelegramWorkerError(f"Telegram API вернул HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TelegramWorkerError(f"Сетевой запрос Telegram не выполнен ({type(exc).__name__}).") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise TelegramWorkerError("Ответ Telegram превышает допустимый размер.")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise TelegramWorkerError("Telegram вернул некорректный JSON.") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise TelegramWorkerError("Telegram API отклонил запрос.")
        return result

    def _network_ready(self) -> bool:
        if not self.require_proxy:
            return True
        if not self.proxy_url:
            self._status("Telegram остановлен: не настроен обязательный локальный HTTP-прокси.")
            return False
        try:
            health = self._network_checker(self.proxy_url, self.health_url)
        except Exception as exc:
            self._status(f"Telegram ожидает доступный прокси ({type(exc).__name__}).")
            return False
        if not getattr(health, "ok", False):
            self._status("Telegram ожидает: HTTPS-проверка через прокси не прошла.")
            return False
        self._status(f"Прокси проверен ({getattr(health, 'latency_ms', 0)} мс). Telegram подключается.")
        return True

    @staticmethod
    def _command_text(message: dict[str, Any]) -> str:
        text = message.get("text")
        if not isinstance(text, str):
            return ""
        return text.strip().split(maxsplit=1)[0].casefold()

    def _authorized(self, message: dict[str, Any]) -> tuple[int | None, int | None]:
        sender = message.get("from")
        chat = message.get("chat")
        user_id = sender.get("id") if isinstance(sender, dict) else None
        chat_id = chat.get("id") if isinstance(chat, dict) else None
        if (
            isinstance(user_id, bool) or not isinstance(user_id, int)
            or isinstance(chat_id, bool) or not isinstance(chat_id, int)
        ):
            return None, None
        if user_id not in self.allowed_user_ids or chat_id not in self.allowed_chat_ids:
            return None, None
        return user_id, chat_id

    def _execute_safe_tool(self, tool_name: str) -> str:
        if tool_name not in self.allowed_tools:
            return "Эта команда отключена в матрице разрешений Telegram."
        spec = self.registry.get_spec(tool_name)
        if spec is None or spec.risk != RiskLevel.SAFE:
            return "Инструмент не прошёл проверку политики безопасности."
        result = self.registry.execute(tool_name, {})
        return result.output[:MAX_MESSAGE_LENGTH]

    def _handle_message(self, message: dict[str, Any]) -> tuple[int, str] | None:
        _user_id, chat_id = self._authorized(message)
        if chat_id is None:
            return None
        command = self._command_text(message)
        if command in {"/start", "/help"}:
            return chat_id, (
                "Hellsaiz PC AI · локальный бот\n"
                "/status — состояние бота\n"
                "/time — локальное время (если разрешено)\n"
                "/system — сведения о системе (если разрешено)\n"
                "/reminders — активные напоминания (если разрешено)\n"
                "Бот не запускает приложения, команды оболочки или произвольные скрипты."
            )
        if command == "/status":
            return chat_id, f"Hellsaiz PC AI {self.app_version}: Telegram worker работает. LLM не используется."
        tool_name = self.COMMAND_TO_TOOL.get(command)
        if tool_name is None:
            return chat_id, "Неизвестная команда. Отправь /help."
        return chat_id, self._execute_safe_tool(tool_name)

    def _send_message(self, chat_id: int, text: str) -> None:
        clean_text = text[:MAX_MESSAGE_LENGTH] or "Нет данных."
        self._api_call("sendMessage", {"chat_id": chat_id, "text": clean_text})

    def run(self) -> None:
        if not self.allowed_user_ids or not self.allowed_chat_ids:
            self._status("Telegram выключен: нет разрешённых user ID/chat ID.")
            return
        if self.require_proxy and not self.proxy_url:
            self._status("Telegram выключен: обязательный прокси не настроен.")
            return
        try:
            if not self._network_ready():
                while not self._stop_event.wait(self.network_retry_seconds):
                    if self._network_ready():
                        break
                else:
                    return
                if not self._network_ready():
                    self._status("Telegram остаётся на паузе: прокси недоступен.")
                    return
            self._api_call("getMe", {})
        except TelegramWorkerError as exc:
            self._status(f"Telegram не запущен: {exc}")
            return
        self._status("Telegram worker подключён; доступ ограничен разрешёнными ID и командами.")
        backoff = 3
        while not self._stop_event.is_set():
            try:
                payload: dict[str, Any] = {
                    "timeout": POLL_TIMEOUT_SECONDS,
                    "limit": 50,
                    "allowed_updates": ["message"],
                }
                if self._offset is not None:
                    payload["offset"] = self._offset
                result = self._api_call("getUpdates", payload)
                updates = result.get("result", [])
                if not isinstance(updates, list):
                    raise TelegramWorkerError("Telegram вернул некорректный список updates.")
                for update in updates:
                    if self._stop_event.is_set():
                        break
                    if not isinstance(update, dict):
                        continue
                    update_id = update.get("update_id")
                    if isinstance(update_id, int) and not isinstance(update_id, bool):
                        self._offset = max(self._offset or 0, update_id + 1)
                    message = update.get("message")
                    if not isinstance(message, dict):
                        continue
                    response = self._handle_message(message)
                    if response is not None:
                        self._send_message(response[0], response[1])
                backoff = 3
            except TelegramWorkerError as exc:
                message = str(exc)
                self._status(message)
                if "HTTP 401" in message or "HTTP 409" in message:
                    return
                if self._stop_event.wait(backoff):
                    return
                backoff = min(backoff * 2, 60)
            except Exception as exc:
                logging.exception("Unexpected Telegram worker failure")
                self._status(f"Telegram worker: внутренняя ошибка ({type(exc).__name__}).")
                if self._stop_event.wait(backoff):
                    return
                backoff = min(backoff * 2, 60)
        self._status("Telegram worker остановлен.")

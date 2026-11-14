from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hellsaiz_pc_ai.secure_store import (
    SecureStoreError as SecureStoreError,
    delete_secret,
    load_secret,
    save_secret,
)


SCHEMA_VERSION = 1
MAX_ALLOWED_IDS = 100
AVAILABLE_SAFE_TOOLS = {
    "get_local_time",
    "get_system_info",
    "list_reminders",
}
BOT_TOKEN_PATTERN = re.compile(r"^[0-9]{5,20}:[A-Za-z0-9_-]{20,128}$")


@dataclass
class TelegramSettings:
    enabled: bool = False
    allowed_user_ids: list[int] = field(default_factory=list)
    allowed_chat_ids: list[int] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    token: str = ""


def validate_bot_token(token: str) -> str:
    if not isinstance(token, str) or not BOT_TOKEN_PATTERN.fullmatch(token.strip()):
        raise ValueError("Укажи корректный токен Telegram-бота из BotFather.")
    return token.strip()


def _parse_ids(value: Any, field_name: str) -> list[int]:
    if not isinstance(value, list) or len(value) > MAX_ALLOWED_IDS:
        raise ValueError(f"{field_name} должен содержать не более {MAX_ALLOWED_IDS} ID.")
    parsed: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item == 0:
            raise ValueError(f"{field_name} содержит некорректный числовой ID.")
        if item not in parsed:
            parsed.append(item)
    return parsed


def _normalize_settings(raw: Any) -> TelegramSettings:
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Настройки Telegram имеют неподдерживаемую схему.")
    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("Флаг enabled должен быть логическим значением.")
    users = _parse_ids(raw.get("allowed_user_ids", []), "allowed_user_ids")
    chats = _parse_ids(raw.get("allowed_chat_ids", []), "allowed_chat_ids")
    if any(value < 0 for value in users):
        raise ValueError("allowed_user_ids может содержать только положительные ID пользователей.")
    # Telegram group and supergroup chat IDs are negative by design.
    # Chat IDs may be signed; zero is already rejected by _parse_ids.
    tools = raw.get("allowed_tools", [])
    if not isinstance(tools, list) or len(tools) > len(AVAILABLE_SAFE_TOOLS):
        raise ValueError("allowed_tools имеет некорректный формат.")
    if any(not isinstance(item, str) or item not in AVAILABLE_SAFE_TOOLS for item in tools):
        raise ValueError("Telegram может разрешать только зарегистрированные безопасные инструменты.")
    return TelegramSettings(enabled, users, chats, list(dict.fromkeys(tools)))


def load_settings(path: Path) -> TelegramSettings:
    token_path = path.with_name("telegram_token.dpapi")
    if not path.is_file():
        return TelegramSettings(token=load_secret(token_path))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Не удалось прочитать настройки Telegram: {exc}") from exc
    normalized = _normalize_settings(raw)
    normalized.token = load_secret(token_path)
    return normalized


def delete_saved_token(path: Path) -> None:
    """Explicitly delete the separately protected bot token."""
    delete_secret(path.with_name("telegram_token.dpapi"))


def save_settings(path: Path, settings: TelegramSettings) -> None:
    normalized = _normalize_settings({
        "schema_version": SCHEMA_VERSION,
        "enabled": settings.enabled,
        "allowed_user_ids": settings.allowed_user_ids,
        "allowed_chat_ids": settings.allowed_chat_ids,
        "allowed_tools": settings.allowed_tools,
    })
    token_path = path.with_name("telegram_token.dpapi")
    token_value = validate_bot_token(settings.token) if settings.token.strip() else ""
    if token_value:
        save_secret(token_path, token_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps({
            "schema_version": SCHEMA_VERSION,
            "enabled": normalized.enabled,
            "allowed_user_ids": normalized.allowed_user_ids,
            "allowed_chat_ids": normalized.allowed_chat_ids,
            "allowed_tools": normalized.allowed_tools,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    settings.enabled = normalized.enabled
    settings.allowed_user_ids[:] = normalized.allowed_user_ids
    settings.allowed_chat_ids[:] = normalized.allowed_chat_ids
    settings.allowed_tools[:] = normalized.allowed_tools
    settings.token = token_value

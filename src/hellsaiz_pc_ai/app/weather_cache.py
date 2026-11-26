"""Last successful weather report, cached next to the user settings."""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from hellsaiz_pc_ai.config import user_data_dir

CACHE_NAME = "weather_last.json"


def weather_cache_path() -> Path:
    """Cache lives in user_data_dir(): never in the temp directory."""
    return user_data_dir() / CACHE_NAME


def save_weather_cache(payload: dict[str, Any]) -> None:
    data = dict(payload)
    data.setdefault("updated_at", datetime.now().isoformat(timespec="seconds"))
    path = weather_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            json.dump(data, handle, ensure_ascii=False)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(path)
    except OSError:
        logging.warning("Weather cache could not be written", exc_info=True)


def load_weather_cache() -> dict[str, Any] | None:
    try:
        raw = json.loads(weather_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def updated_label(payload: dict[str, Any]) -> str:
    stamp = str(payload.get("updated_at") or "")
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return "Обновлено ранее"
    return f"Обновлено {moment.strftime('%H:%M')}"

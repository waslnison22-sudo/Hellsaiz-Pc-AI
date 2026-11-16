from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def save_ai_profile(path: Path, data: dict[str, Any]) -> None:
    """Persist ai_profile.json atomically without truncating the previous valid file."""
    if not isinstance(data, dict):
        raise ValueError("Профиль помощника должен быть JSON-объектом.")
    try:
        serialized = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Не удалось подготовить профиль помощника: {exc}") from exc

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise

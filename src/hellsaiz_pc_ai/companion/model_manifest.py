from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from hellsaiz_pc_ai.companion.contracts import CompanionModelInfo


SUPPORTED_FORMATS = {"live2d", "vrm", "sprite", "custom"}
MODEL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


def _safe_relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{field} must be a non-empty relative path.")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{field} must not escape the model directory.")
    if path.parts and ":" in path.parts[0]:
        raise ValueError(f"{field} must not contain a drive prefix.")
    return path.as_posix()


def validate_model_manifest(raw: Any, manifest_path: Path) -> CompanionModelInfo:
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Companion model manifest has an unsupported schema.")
    model_id = raw.get("model_id")
    if not isinstance(model_id, str) or not MODEL_ID_PATTERN.fullmatch(model_id):
        raise ValueError("model_id must use 2-64 lowercase letters, digits, dots, underscores or hyphens.")
    display_name = raw.get("display_name")
    if not isinstance(display_name, str) or not 1 <= len(display_name.strip()) <= 80:
        raise ValueError("display_name must contain 1-80 characters.")
    format_id = raw.get("format_id")
    if format_id not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported companion model format: {format_id}.")
    renderer_id = raw.get("renderer_id")
    if not isinstance(renderer_id, str) or not MODEL_ID_PATTERN.fullmatch(renderer_id):
        raise ValueError("renderer_id must be a stable renderer adapter identifier.")
    entrypoint = _safe_relative_path(raw.get("entrypoint"), "entrypoint")
    model_root = manifest_path.parent.resolve()
    candidate = (model_root / Path(*PurePosixPath(entrypoint).parts)).resolve()
    if model_root not in candidate.parents or not candidate.is_file():
        raise ValueError("Companion model entrypoint is missing or escapes the model directory.")
    return CompanionModelInfo(
        model_id=model_id,
        display_name=display_name.strip(),
        format_id=format_id,
        renderer_id=renderer_id,
        entrypoint=entrypoint,
        manifest_path=str(manifest_path.resolve()),
    )


def load_model_manifest(manifest_path: Path) -> CompanionModelInfo:
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read companion model manifest: {exc}") from exc
    return validate_model_manifest(raw, manifest_path)

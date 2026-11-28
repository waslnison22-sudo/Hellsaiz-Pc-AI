"""Persona runtime glue: paths and the effective system prompt.

Kept separate from `desktop.py` so every assistant construction site (startup,
provider switch, settings rebuild) can use the same prompt without duplicating
the merge logic or depending on closure scope.
"""

from __future__ import annotations

from pathlib import Path

from hellsaiz_pc_ai.app import persona as persona_module
from hellsaiz_pc_ai.config import Settings


def persona_path(settings: Settings) -> Path:
    return settings.workflows_path.parent / "personas.json"


def companion_models_dir(settings: Settings) -> Path:
    return settings.workflows_path.parent / "companion_models"


def companion_active_path(settings: Settings) -> Path:
    return settings.workflows_path.parent / "companion_active.json"


def current_system_prompt(settings: Settings) -> str:
    """Base prompt plus the active persona block (owner settings)."""
    base = settings.llm.system_prompt or ""
    try:
        active = persona_module.active_persona(persona_path(settings))
    except (OSError, ValueError):
        return base
    return f"{base}\n\n{persona_module.build_system_prompt(active)}".strip()

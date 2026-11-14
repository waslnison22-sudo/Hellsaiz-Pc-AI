"""Optional, renderer-agnostic companion foundation."""

from hellsaiz_pc_ai.companion.controller import CompanionController
from hellsaiz_pc_ai.companion.contracts import (
    CompanionEmotion,
    CompanionMode,
    CompanionSnapshot,
    CompanionViseme,
)

__all__ = [
    "CompanionController",
    "CompanionEmotion",
    "CompanionMode",
    "CompanionSnapshot",
    "CompanionViseme",
]

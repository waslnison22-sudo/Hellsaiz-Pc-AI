from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class CompanionMode(StrEnum):
    HIDDEN = "hidden"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


class CompanionEmotion(StrEnum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    SURPRISED = "surprised"
    ANGRY = "angry"
    CONFUSED = "confused"
    CURIOUS = "curious"


class CompanionViseme(StrEnum):
    SILENCE = "sil"
    A = "A"
    I = "I"
    U = "U"
    E = "E"
    O = "O"


@dataclass(frozen=True)
class CompanionSnapshot:
    mode: CompanionMode = CompanionMode.HIDDEN
    emotion: CompanionEmotion = CompanionEmotion.NEUTRAL
    viseme: CompanionViseme = CompanionViseme.SILENCE
    emotion_weight: float = 1.0
    mouth_weight: float = 0.0
    gaze_x: float = 0.0
    gaze_y: float = 0.0
    status_text: str = ""

    def __post_init__(self) -> None:
        for name in ("emotion_weight", "mouth_weight"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1.")
        for name in ("gaze_x", "gaze_y"):
            value = getattr(self, name)
            if not -1.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between -1 and 1.")
        if len(self.status_text) > 240:
            raise ValueError("status_text must be at most 240 characters.")
        if self.mode != CompanionMode.SPEAKING and self.viseme != CompanionViseme.SILENCE:
            raise ValueError("A viseme can only be active while the companion is speaking.")
        if self.viseme == CompanionViseme.SILENCE and self.mouth_weight != 0.0:
            raise ValueError("A silent mouth must have zero mouth weight.")


@dataclass(frozen=True)
class CompanionModelInfo:
    model_id: str
    display_name: str
    format_id: str
    renderer_id: str
    entrypoint: str
    manifest_path: str


@runtime_checkable
class CompanionRenderer(Protocol):
    """Renderer adapter contract. Implementations must own no assistant logic."""

    def load_model(self, model_directory: str, entrypoint: str) -> None: ...

    def apply_snapshot(self, snapshot: CompanionSnapshot) -> None: ...

    def render_status(self) -> dict[str, Any]: ...

    def close(self) -> None: ...

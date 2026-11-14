from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from hellsaiz_pc_ai.companion.contracts import (
    CompanionEmotion,
    CompanionMode,
    CompanionSnapshot,
    CompanionViseme,
)


SnapshotListener = Callable[[CompanionSnapshot], None]


class CompanionController:
    """Thread-safe state bridge between assistant events and any avatar renderer."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot = CompanionSnapshot()
        self._listeners: set[SnapshotListener] = set()

    def snapshot(self) -> CompanionSnapshot:
        with self._lock:
            return self._snapshot

    def subscribe(self, listener: SnapshotListener) -> Callable[[], None]:
        with self._lock:
            self._listeners.add(listener)
            initial = self._snapshot
        self._notify_one(listener, initial)

        def unsubscribe() -> None:
            with self._lock:
                self._listeners.discard(listener)

        return unsubscribe

    def _notify_one(self, listener: SnapshotListener, snapshot: CompanionSnapshot) -> None:
        try:
            listener(snapshot)
        except Exception:
            logging.exception("Companion snapshot listener failed.")

    def _update(self, **changes: object) -> CompanionSnapshot:
        with self._lock:
            updated = CompanionSnapshot(**{**self._snapshot.__dict__, **changes})
            self._snapshot = updated
            listeners = tuple(self._listeners)
        for listener in listeners:
            self._notify_one(listener, updated)
        return updated

    def set_mode(self, mode: CompanionMode, status_text: str = "") -> CompanionSnapshot:
        if mode != CompanionMode.SPEAKING:
            return self._update(
                mode=mode,
                viseme=CompanionViseme.SILENCE,
                mouth_weight=0.0,
                status_text=status_text,
            )
        return self._update(mode=mode, status_text=status_text)

    def set_emotion(
        self,
        emotion: CompanionEmotion,
        weight: float = 1.0,
    ) -> CompanionSnapshot:
        return self._update(emotion=emotion, emotion_weight=weight)

    def set_viseme(
        self,
        viseme: CompanionViseme,
        weight: float = 1.0,
    ) -> CompanionSnapshot:
        current = self.snapshot()
        if current.mode != CompanionMode.SPEAKING and viseme != CompanionViseme.SILENCE:
            raise ValueError("Set companion mode to SPEAKING before emitting a viseme.")
        mouth_weight = 0.0 if viseme == CompanionViseme.SILENCE else weight
        return self._update(viseme=viseme, mouth_weight=mouth_weight)

    def set_gaze(self, x: float, y: float) -> CompanionSnapshot:
        return self._update(gaze_x=x, gaze_y=y)

    def reset(self) -> CompanionSnapshot:
        return self._update(
            mode=CompanionMode.IDLE,
            emotion=CompanionEmotion.NEUTRAL,
            viseme=CompanionViseme.SILENCE,
            emotion_weight=1.0,
            mouth_weight=0.0,
            gaze_x=0.0,
            gaze_y=0.0,
            status_text="",
        )

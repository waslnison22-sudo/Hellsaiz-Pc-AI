"""Bridge from assistant events to the companion controller.

The bridge maps worker lifecycle signals to companion modes so any overlay
renderer can animate "listening → thinking → speaking" without knowing about
the chat pipeline. Import this module lazily from the desktop shell; it must
never import Qt threading or the companion overlay itself.
"""

from __future__ import annotations

import logging

from hellsaiz_pc_ai.companion.contracts import CompanionEmotion, CompanionMode
from hellsaiz_pc_ai.companion.controller import CompanionController


class CompanionEventBridge:
    """Maps semantic assistant events onto the companion snapshot controller."""

    def __init__(self, controller: CompanionController) -> None:
        self._controller = controller

    def listening(self) -> None:
        self._controller.set_mode(CompanionMode.LISTENING, "Слушаю")

    def thinking(self) -> None:
        self._controller.set_mode(CompanionMode.THINKING, "Думаю")

    def speaking(self, text: str = "") -> None:
        status = text.strip()[:240] if text.strip() else "Говорю"
        self._controller.set_mode(CompanionMode.SPEAKING, status)

    def error(self) -> None:
        self._controller.set_mode(CompanionMode.ERROR, "Что-то сломалось")
        self._controller.set_emotion(CompanionEmotion.CONFUSED)

    def settled(self) -> None:
        self._controller.set_mode(CompanionMode.IDLE, "")

    def reset(self) -> None:
        self._controller.reset()

    # -- Signal adapters (accept the argument shapes Qt signals deliver) -------

    def connect_worker(self, started, finished, failed) -> None:
        """Wire Qt signals of a worker (or equivalent callables) to the modes."""
        try:
            started.connect(lambda *_: self.thinking())
            finished.connect(lambda *_: self.settled())
            failed.connect(lambda *_: self.error())
        except AttributeError:
            logging.warning("Companion bridge: worker has no expected signals.")

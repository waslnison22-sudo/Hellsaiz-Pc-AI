"""Companion affinity: daily usage points, five levels and JSON persistence.

Pure Python (no Qt): it only reads and merges the companion.json payload, so the
overlay can keep owning position/scale/hidden without clobbering these fields.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

LEVELS: tuple[str, ...] = ("Знакомый", "Спутник", "Помощник", "Партнёр", "Свой")
DAILY_POINTS = 5
REMINDER_POINTS = 2
SCENARIO_POINTS = 3
INTERACTION_POINTS = 1
POINTS_PER_LEVEL = 20
MAX_POINTS = 200


class AffinityTracker:
    """Counts long-term closeness; daily usage matters more than minute counts."""

    def __init__(
        self,
        state_path: Path | None = None,
        *,
        today: Callable[[], str] | None = None,
    ) -> None:
        self._path = Path(state_path) if state_path is not None else None
        self._today = today or (lambda: datetime.now().strftime("%Y-%m-%d"))
        self._points = 0
        self._last_seen = ""
        self._listeners: list[Callable[[int, str], None]] = []
        self._load()

    # -- persistence -----------------------------------------------------
    def _read_payload(self) -> dict:
        if self._path is None or not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            logging.debug("Affinity state is unreadable; starting fresh.")
            return {}
        return raw if isinstance(raw, dict) else {}

    def _load(self) -> None:
        payload = self._read_payload()
        points = payload.get("affinity_points")
        if isinstance(points, int) and not isinstance(points, bool) and points >= 0:
            self._points = min(points, MAX_POINTS)
        last_seen = payload.get("last_seen_date")
        if isinstance(last_seen, str):
            self._last_seen = last_seen
        if not isinstance(points, int):
            self._points = 0

    def save(self) -> None:
        if self._path is None:
            return
        payload = self._read_payload()
        payload["affinity_points"] = self._points
        payload["affinity_level"] = self.level_index
        payload["last_seen_date"] = self._last_seen
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(self._path)
        except OSError:
            logging.exception("Could not persist companion affinity.")

    # -- API -------------------------------------------------------------
    @property
    def points(self) -> int:
        return self._points

    @property
    def level_index(self) -> int:
        return min(self._points // POINTS_PER_LEVEL, len(LEVELS) - 1)

    def level(self) -> str:
        return LEVELS[self.level_index]

    def subscribe(self, listener: Callable[[int, str], None]) -> Callable[[], None]:
        """Register ``listener(points, level)``; returns an unsubscribe callable."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener(self._points, self.level())
            except Exception:  # noqa: BLE001 - a listener must not break the counter
                logging.exception("Affinity listener failed.")

    def add_points(self, amount: int = INTERACTION_POINTS) -> tuple[int, str, bool]:
        """Add points, persist and notify. Returns (points, level, level_raised)."""
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError("Affinity points must be an integer.")
        previous_level = self.level_index
        self._points = max(0, min(self._points + amount, MAX_POINTS))
        raised = self.level_index > previous_level
        self.save()
        self._notify()
        return self._points, self.level(), raised

    def register_daily_activity(self) -> bool:
        """Once per calendar day the companion gets the daily closeness bonus."""
        today = self._today()
        if self._last_seen == today:
            return False
        self._last_seen = today
        self.add_points(DAILY_POINTS)
        return True

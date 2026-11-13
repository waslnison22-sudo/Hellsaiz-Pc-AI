from __future__ import annotations

from collections.abc import Callable
from typing import Any


class HotkeyUnavailableError(RuntimeError):
    pass


_MODIFIERS = {
    "ctrl": "<ctrl>",
    "alt": "<alt>",
    "shift": "<shift>",
    "win": "<cmd>",
}
_SPECIAL_KEYS = {
    "space": "<space>",
    "enter": "<enter>",
    "tab": "<tab>",
}


def to_pynput_combo(value: str) -> str:
    """Convert Ctrl+Alt+K notation to pynput GlobalHotKeys syntax."""
    parts = [part.strip() for part in value.split("+")]
    if not parts or any(not part for part in parts):
        raise ValueError("Hotkey cannot contain empty key names.")
    converted: list[str] = []
    for part in parts:
        lowered = part.casefold()
        if lowered in _MODIFIERS:
            converted.append(_MODIFIERS[lowered])
        elif lowered in _SPECIAL_KEYS:
            converted.append(_SPECIAL_KEYS[lowered])
        elif lowered.startswith("f") and lowered[1:].isdigit():
            number = int(lowered[1:])
            if not 1 <= number <= 12:
                raise ValueError("Function key must be F1..F12.")
            converted.append(f"<f{number}>")
        elif len(part) == 1 and part.isalnum():
            converted.append(part.lower())
        else:
            raise ValueError(f"Unsupported hotkey key: {part}")
    if len(converted) < 2 or not any(part in _MODIFIERS.values() for part in converted):
        raise ValueError("A global hotkey must include at least one modifier.")
    return "+".join(converted)


class GlobalHotkeyService:
    """Optional global hotkey listener. pynput is imported only when started."""

    def __init__(self, bindings: dict[str, Callable[[], None]]) -> None:
        self.bindings = dict(bindings)
        self._listener: Any | None = None

    def start(self) -> None:
        if not self.bindings:
            return
        try:
            from pynput.keyboard import GlobalHotKeys
        except ImportError as exc:
            raise HotkeyUnavailableError(
                'Global hotkeys require the Windows extras: pip install -e ".[windows]".'
            ) from exc
        mapping = {to_pynput_combo(combo): callback for combo, callback in self.bindings.items()}
        try:
            self._listener = GlobalHotKeys(mapping)
            self._listener.start()
        except Exception as exc:
            raise HotkeyUnavailableError(f"Could not register global hotkeys: {exc}") from exc

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

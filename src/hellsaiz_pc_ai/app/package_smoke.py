from __future__ import annotations

import importlib
from collections.abc import Callable


PACKAGED_RUNTIME_MODULES = (
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "PySide6.QtWebEngineWidgets",
    "cryptography.hazmat.primitives.asymmetric.ed25519",
    "numpy",
    "sounddevice",
    "vosk",
    "piper",
    "onnxruntime",
    "pyttsx3",
    "psutil",
    "pycaw.pycaw",
    "pynput",
)


def check_packaged_runtime(
    importer: Callable[[str], object] = importlib.import_module,
) -> list[tuple[str, str]]:
    """Import critical packaged modules without touching audio devices or user data."""
    failures: list[tuple[str, str]] = []
    for module_name in PACKAGED_RUNTIME_MODULES:
        try:
            importer(module_name)
        except Exception as exc:
            failures.append((module_name, f"{type(exc).__name__}: {exc}"))
    return failures

from __future__ import annotations

import importlib
from collections.abc import Callable


# Only require modules that the desktop runtime actually imports. QtWebEngine
# is not used by the current UI and is not part of the base PySide6 runtime.
PACKAGED_RUNTIME_MODULES = (
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "hellsaiz_pc_ai.providers.gigachat",
    "hellsaiz_pc_ai.tools.ui_automation",
    "hellsaiz_pc_ai.tools.file_system",
    "hellsaiz_pc_ai.app.file_access",
    "hellsaiz_pc_ai.companion.controller",
    "hellsaiz_pc_ai.companion.model_manifest",
    "hellsaiz_pc_ai.startup_task",
    "hellsaiz_pc_ai.telegram.config",
    "hellsaiz_pc_ai.telegram.worker",
    "hellsaiz_pc_ai.tools.screen_ocr",
    "hellsaiz_pc_ai.tools.ocr_models",
    "mss",
    "rapidocr",
    "onnxruntime",
    "pywinauto",
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
    progress: Callable[[str], None] | None = None,
) -> list[tuple[str, str]]:
    """Import critical packaged modules without touching audio devices or user data."""
    failures: list[tuple[str, str]] = []
    for module_name in PACKAGED_RUNTIME_MODULES:
        if progress is not None:
            progress(f"Checking {module_name}")
        try:
            importer(module_name)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            failures.append((module_name, detail))
            if progress is not None:
                progress(f"FAILED {module_name}: {detail}")
        else:
            if progress is not None:
                progress(f"OK {module_name}")
    return failures

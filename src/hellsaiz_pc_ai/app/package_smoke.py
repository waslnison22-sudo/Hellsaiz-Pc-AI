from __future__ import annotations

import importlib
from collections.abc import Callable


# Only require modules that the desktop runtime actually imports. QtWebEngine
# is not used by the current UI and is not part of the base PySide6 runtime.
PACKAGED_RUNTIME_MODULES = (
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "hellsaiz_pc_ai.app.desktop",
    "hellsaiz_pc_ai.app.ui_workers",
    "hellsaiz_pc_ai.app.workflow_studio",
    "hellsaiz_pc_ai.workflows.qt_canvas",
    "hellsaiz_pc_ai.workflows.studio_model",
    "hellsaiz_pc_ai.providers.gigachat",
    "hellsaiz_pc_ai.tools.ui_automation",
    "hellsaiz_pc_ai.tools.file_system",
    "hellsaiz_pc_ai.app.file_access",
    "hellsaiz_pc_ai.companion.controller",
    "hellsaiz_pc_ai.companion.model_manifest",
    "hellsaiz_pc_ai.startup_task",
    "hellsaiz_pc_ai.telegram.config",
    "hellsaiz_pc_ai.telegram.worker",
    "hellsaiz_pc_ai.network.v2raytun",
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
    "pyttsx3",
    "psutil",
    "pycaw.pycaw",
    "pynput",
)


def check_icon_rendering() -> list[str]:
    """Render one vendored Lucide icon; proves QtSvg made it into the bundle."""
    try:
        from hellsaiz_pc_ai.app.icons import load_icon
    except Exception as exc:  # pragma: no cover - bundle-specific
        return [f"icons module could not be imported: {exc}"]

    icon = load_icon("mic", "#F2EFEA")
    if icon.isNull():
        return ["Lucide icon 'mic' could not be loaded (missing SVG or QtSvg?)"]
    pixmap = icon.pixmap(24, 24)
    if pixmap.isNull() or pixmap.width() < 16:
        return ["Lucide icon 'mic' rendered an empty pixmap"]
    image = pixmap.toImage()
    opaque = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )
    if opaque < 20:
        return [f"Lucide icon 'mic' rendered only {opaque} visible pixels"]
    return []


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

"""Vendored Lucide icon assets must all load and render."""

from __future__ import annotations

import pytest

try:  # PySide6 GUI libraries are absent on headless Linux runners.
    from PySide6.QtWidgets import QApplication

    from hellsaiz_pc_ai.app.icons import available_icons, load_icon

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

_requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


@_requires_qt
def test_every_vendored_icon_renders():
    QApplication.instance() or QApplication([])
    names = available_icons()

    assert "bell" in names
    assert "volume-2" in names
    assert "circle-check" in names
    assert "user-round" in names

    for name in names:
        icon = load_icon(name, "#F2EFEA")
        assert icon.isNull() is False, name
        pixmap = icon.pixmap(20, 20)
        assert pixmap.isNull() is False, name
        image = pixmap.toImage()
        visible = sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 0
        )
        assert visible > 5, f"{name} rendered almost nothing"


@_requires_qt
def test_media_icons_load_from_the_vendored_set():
    """The frozen build showed empty play/pause buttons: assets must resolve."""
    QApplication.instance() or QApplication([])

    for name in ("play", "pause", "skip-back", "skip-forward"):
        icon = load_icon(name, "#F2EFEA")
        assert icon.isNull() is False, name
        assert icon.pixmap(16, 16).isNull() is False, name


def test_build_bundles_the_icon_assets():
    """PyInstaller must ship assets/, and the loader must find it when frozen."""
    from pathlib import Path

    pytest.importorskip("PySide6.QtSvg")
    from hellsaiz_pc_ai.app import icons as icons_module

    source = Path(icons_module.__file__).read_text(encoding="utf-8")
    script = (
        Path(__file__).resolve().parents[1] / "scripts" / "build_windows.ps1"
    ).read_text(encoding="utf-8")

    assert "_MEIPASS" in source
    assert "--add-data" in script
    assert "assets;assets" in script
    assert icons_module.ICON_DIR.is_dir()

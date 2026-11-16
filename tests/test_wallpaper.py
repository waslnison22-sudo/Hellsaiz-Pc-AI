import json
from pathlib import Path

import pytest

from hellsaiz_pc_ai.app.wallpaper import WallpaperError, WallpaperStore


def make_png(path: Path) -> Path:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return path


def test_import_wallpaper_copies_to_private_library_and_persists(tmp_path: Path):
    source = make_png(tmp_path / "desktop.png")
    store = WallpaperStore(tmp_path / "profile")

    imported = store.import_wallpaper(source)

    assert imported.parent == store.directory
    assert imported.read_bytes() == source.read_bytes()
    assert store.active_wallpaper() == imported
    assert json.loads(store.preferences_path.read_text())["filename"] == imported.name


def test_clear_restores_black_default(tmp_path: Path):
    store = WallpaperStore(tmp_path / "profile")
    store.import_wallpaper(make_png(tmp_path / "wall.png"))

    store.clear()

    assert store.active_wallpaper() is None


def test_import_rejects_non_images_and_unsupported_suffixes(tmp_path: Path):
    store = WallpaperStore(tmp_path / "profile")
    invalid = tmp_path / "not-image.png"
    invalid.write_text("not an image", encoding="utf-8")
    with pytest.raises(WallpaperError):
        store.import_wallpaper(invalid)

    unsupported = tmp_path / "image.txt"
    unsupported.write_text("text", encoding="utf-8")
    with pytest.raises(WallpaperError):
        store.import_wallpaper(unsupported)


def test_active_wallpaper_rejects_path_traversal(tmp_path: Path):
    store = WallpaperStore(tmp_path / "profile")
    store.preferences_path.parent.mkdir(parents=True)
    store.preferences_path.write_text('{"filename":"../secret.png"}', encoding="utf-8")

    assert store.active_wallpaper() is None


def test_fit_mode_defaults_to_fill_and_persists(tmp_path: Path):
    store = WallpaperStore(tmp_path / "profile")

    assert store.fit_mode() == "fill"

    store.set_fit_mode("fit")
    assert store.fit_mode() == "fit"

    store.set_fit_mode("stretch")
    assert json.loads(store.preferences_path.read_text())["fit_mode"] == "stretch"


def test_set_fit_mode_rejects_unknown_values(tmp_path: Path):
    store = WallpaperStore(tmp_path / "profile")

    with pytest.raises(WallpaperError):
        store.set_fit_mode("bogus")


def test_import_wallpaper_preserves_fit_mode(tmp_path: Path):
    store = WallpaperStore(tmp_path / "profile")
    store.set_fit_mode("fit")
    store.import_wallpaper(make_png(tmp_path / "wall.png"))

    assert store.fit_mode() == "fit"


def test_clear_preserves_fit_mode(tmp_path: Path):
    store = WallpaperStore(tmp_path / "profile")
    store.set_fit_mode("stretch")
    store.import_wallpaper(make_png(tmp_path / "wall.png"))
    store.clear()

    assert store.fit_mode() == "stretch"
    assert store.active_wallpaper() is None

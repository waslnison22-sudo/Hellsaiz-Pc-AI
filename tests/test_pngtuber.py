"""PNGTuber import: validation, degradation, registry and renderer contracts."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from hellsaiz_pc_ai.companion import pngtuber


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return path


def write_png(path: Path) -> None:
    from PySide6.QtGui import QColor, QImage

    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(QColor("#00000000"))
    image.save(str(path), "PNG")


def test_import_full_pack(tmp_path: Path):
    archive = make_zip(
        tmp_path / "Wolf-Girl.zip",
        {
            "Wolf-Girl/idle.png": PNG_BYTES,
            "Wolf-Girl/talking.png": PNG_BYTES,
            "Wolf-Girl/blink.png": PNG_BYTES,
            "Wolf-Girl/blink-talking.png": PNG_BYTES,
            "Wolf-Girl/README.txt": b"docs",
        },
    )
    models = tmp_path / "models"

    folder = pngtuber.import_pngtuber_zip(archive, models)

    assert folder.is_dir()
    manifest = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    assert manifest["model_id"] == "wolf-girl"
    assert manifest["format_id"] == "sprite"
    assert manifest["renderer_id"] == "pngtuber"
    assert set(manifest["states"]) == {"idle", "talk", "blink", "blink_talk"}


def test_missing_frames_degrade_not_reject(tmp_path: Path):
    archive = make_zip(tmp_path / "mini.zip", {"mini/idle.png": PNG_BYTES})

    folder = pngtuber.import_pngtuber_zip(archive, tmp_path / "models")

    manifest = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    assert manifest["states"] == {"idle": "idle.png"}


def test_missing_idle_is_rejected(tmp_path: Path):
    archive = make_zip(tmp_path / "bad.zip", {"bad/talking.png": PNG_BYTES})

    with pytest.raises(pngtuber.ModelImportError, match="idle"):
        pngtuber.import_pngtuber_zip(archive, tmp_path / "models")


def test_executables_are_rejected(tmp_path: Path):
    archive = make_zip(
        tmp_path / "evil.zip",
        {"evil/idle.png": PNG_BYTES, "evil/payload.exe": b"MZ"},
    )

    with pytest.raises(pngtuber.ModelImportError):
        pngtuber.import_pngtuber_zip(archive, tmp_path / "models")


def test_path_traversal_is_rejected(tmp_path: Path):
    archive = make_zip(
        tmp_path / "trav.zip",
        {"../evil/idle.png": PNG_BYTES},
    )

    with pytest.raises(pngtuber.ModelImportError):
        pngtuber.import_pngtuber_zip(archive, tmp_path / "models")


def test_two_roots_are_rejected(tmp_path: Path):
    archive = make_zip(
        tmp_path / "two.zip",
        {"a/idle.png": PNG_BYTES, "b/blink.png": PNG_BYTES},
    )

    with pytest.raises(pngtuber.ModelImportError):
        pngtuber.import_pngtuber_zip(archive, tmp_path / "models")


def test_registry_lists_and_deletes(tmp_path: Path):
    archive = make_zip(tmp_path / "pack.zip", {"pack/idle.png": PNG_BYTES})
    models = tmp_path / "models"
    pngtuber.import_pngtuber_zip(archive, models)

    items = pngtuber.list_installed_models(models)
    assert len(items) == 1
    assert items[0]["model_id"] == "pack"
    assert Path(items[0]["preview"]).is_file()

    assert pngtuber.delete_model(models, "pack") is True
    assert pngtuber.list_installed_models(models) == []


def test_renderer_loads_frames_and_reports_status(tmp_path: Path):
    widgets = pytest.importorskip("PySide6.QtWidgets")
    app = widgets.QApplication.instance() or widgets.QApplication([])
    assert app is not None
    folder = tmp_path / "model"
    folder.mkdir()
    (folder / "model.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_id": "demo",
                "display_name": "Demo",
                "format_id": "sprite",
                "renderer_id": "pngtuber",
                "entrypoint": "idle.png",
                "states": {"idle": "idle.png"},
            }
        ),
        encoding="utf-8",
    )
    write_png(folder / "idle.png")

    renderer = pngtuber.PngTuberRenderer()
    renderer.load_model(str(folder), "idle.png")

    status = renderer.render_status()
    assert status["renderer"] == "pngtuber"
    assert "idle" in status["frames"]

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from hellsaiz_pc_ai.speech import model_library as library


def _write_model_archive(path: Path, *, extra: tuple[str, bytes] | None = None) -> Path:
    entries = {
        f"{library.VOSK_MODEL_ID}/am/final.mdl": b"model",
        f"{library.VOSK_MODEL_ID}/conf/model.conf": b"sample-frequency=16000",
        f"{library.VOSK_MODEL_ID}/graph/words.txt": b"<eps> 0\n",
    }
    if extra is not None:
        entries[extra[0]] = extra[1]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return path


def test_valid_vosk_archive_extracts_to_expected_model_directory(tmp_path: Path):
    archive = _write_model_archive(tmp_path / "model.zip")

    result = library._safe_extract(archive, tmp_path / "extract")

    assert result == tmp_path / "extract" / library.VOSK_MODEL_ID
    assert library.is_valid_vosk_model(result)


def test_vosk_archive_rejects_path_traversal(tmp_path: Path):
    archive = _write_model_archive(
        tmp_path / "unsafe.zip",
        extra=("../outside.txt", b"must not escape"),
    )
    destination = tmp_path / "extract"

    with pytest.raises(library.ModelInstallError, match="путь"):
        library._safe_extract(archive, destination)

    assert not (tmp_path / "outside.txt").exists()


def test_vosk_archive_rejects_unexpected_root(tmp_path: Path):
    archive = tmp_path / "wrong-root.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("other-model/am/final.mdl", b"model")

    with pytest.raises(library.ModelInstallError, match="корневой"):
        library._safe_extract(archive, tmp_path / "extract")


def test_vosk_archive_rejects_symlink_entries(tmp_path: Path):
    archive = _write_model_archive(tmp_path / "symlink.zip")
    link = zipfile.ZipInfo(f"{library.VOSK_MODEL_ID}/am/link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as output:
        output.writestr(link, "../outside")

    with pytest.raises(library.ModelInstallError, match="Символ"):
        library._safe_extract(archive, tmp_path / "extract")


def test_vosk_archive_enforces_extracted_size_limit(tmp_path: Path, monkeypatch):
    archive = _write_model_archive(tmp_path / "large.zip")
    monkeypatch.setattr(library, "MAX_EXTRACTED_BYTES", 10)

    with pytest.raises(library.ModelInstallError, match="лимит"):
        library._safe_extract(archive, tmp_path / "extract")


def test_vosk_installer_downloads_and_activates_model_atomically(tmp_path: Path, monkeypatch):
    destination = tmp_path / "models"

    def fake_download(path: Path):
        _write_model_archive(path)

    monkeypatch.setattr(library, "_download_archive", fake_download)

    installed = library.install_vosk_small_ru(destination)

    assert installed == destination / library.VOSK_MODEL_ID
    assert library.is_valid_vosk_model(installed)
    assert library.install_vosk_small_ru(destination) == installed


def test_vosk_installer_does_not_follow_symlink_target(tmp_path: Path, monkeypatch):
    destination = tmp_path / "models"
    destination.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    (destination / library.VOSK_MODEL_ID).symlink_to(outside, target_is_directory=True)

    with pytest.raises(library.ModelInstallError, match="символической ссылкой"):
        library.install_vosk_small_ru(destination)

    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"

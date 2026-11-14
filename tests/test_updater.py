from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from hellsaiz_pc_ai.updater import (
    ApplyUpdateError,
    _clone_current_version,
    _extract_archive,
    _verify_payload,
)


def _record(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_full_archive_extracts_and_verifies(tmp_path: Path):
    archive_path = tmp_path / "full.zip"
    stage = tmp_path / "stage"
    stage.mkdir()
    payload = {"HellsaizPC_AI.exe": b"binary", "Qt6Core.dll": b"qt-runtime"}
    expected = {}
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, data in payload.items():
            archive.writestr(name, data)
            expected[name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    _extract_archive(archive_path, stage, "full", expected)
    _verify_payload(stage, expected)

    assert (stage / "HellsaizPC_AI.exe").read_bytes() == b"binary"


def test_archive_rejects_path_traversal(tmp_path: Path):
    archive_path = tmp_path / "malicious.zip"
    stage = tmp_path / "stage"
    stage.mkdir()
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", b"escape")

    with pytest.raises(Exception, match="Недопустимый путь"):
        _extract_archive(archive_path, stage, "delta", {})

    assert not (tmp_path / "outside.txt").exists()


def test_payload_hash_mismatch_is_rejected(tmp_path: Path):
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "app.exe").write_bytes(b"tampered")
    expected = {"app.exe": {"size": 8, "sha256": "0" * 64}}

    with pytest.raises(ApplyUpdateError, match="SHA-256"):
        _verify_payload(stage, expected)


def test_delta_staging_does_not_modify_active_version(tmp_path: Path):
    active = tmp_path / "active"
    staged = tmp_path / "staged"
    active.mkdir()
    original = active / "app.exe"
    original.write_bytes(b"old-version")

    _clone_current_version(active, staged)
    (staged / "app.exe").write_bytes(b"new-version")

    assert original.read_bytes() == b"old-version"
    assert (staged / "app.exe").read_bytes() == b"new-version"

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from hellsaiz_pc_ai.update_client import UpdateCheckError, _safe_manifest_path
from hellsaiz_pc_ai.updater import (
    ApplyUpdateError,
    _clone_current_version,
    _extract_archive,
    _verify_payload,
    _wait_for_parent,
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

    with pytest.raises(UpdateCheckError, match="Недопустимый путь"):
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



@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.txt",
        "folder//file.dll",
        "folder/./file.dll",
        "folder/../file.dll",
        "CON.txt",
        "nested/LPT1.log",
        "bad?.dll",
        "bad<name>.dll",
        "trailing./file.dll",
    ],
)
def test_manifest_path_rejects_windows_unsafe_names(unsafe_path: str):
    with pytest.raises(UpdateCheckError):
        _safe_manifest_path(unsafe_path)


def test_wait_for_parent_uses_pointer_sized_windows_handles(monkeypatch):
    import ctypes
    from ctypes import wintypes

    class FakeFunction:
        def __init__(self, result):
            self.result = result
            self.argtypes = None
            self.restype = None
            self.calls = []

        def __call__(self, *args):
            self.calls.append(args)
            return self.result

    class FakeKernel32:
        def __init__(self):
            self.OpenProcess = FakeFunction(0x123456789)
            self.WaitForSingleObject = FakeFunction(0)
            self.CloseHandle = FakeFunction(1)

    kernel32 = FakeKernel32()
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: kernel32, raising=False)
    monkeypatch.setattr("hellsaiz_pc_ai.updater.os.name", "nt")
    _wait_for_parent(1234)

    assert kernel32.OpenProcess.restype is wintypes.HANDLE
    assert kernel32.WaitForSingleObject.calls == [(0x123456789, 120000)]
    assert kernel32.CloseHandle.calls == [(0x123456789,)]

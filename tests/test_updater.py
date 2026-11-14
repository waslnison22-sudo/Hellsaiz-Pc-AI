from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from hellsaiz_pc_ai.update_client import UpdateCheckError, _safe_manifest_path
from hellsaiz_pc_ai import updater
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



@pytest.mark.skipif(__import__("os").name != "nt", reason="The update installer is Windows-only.")
@pytest.mark.parametrize("health_state", ["ok", "fail", "exception"])
def test_full_update_migrates_existing_install_and_preserves_user_data(
    tmp_path: Path, monkeypatch, health_state: str
):
    import json

    install_root = tmp_path / "Hellsaiz PC AI"
    versions = install_root / "versions"
    old_version = versions / "0.1.3"
    old_version.mkdir(parents=True)
    (old_version / "HellsaizPC_AI.exe").write_bytes(b"old-app")
    (install_root / "HellsaizLauncher.exe").write_bytes(b"stable-launcher")
    (install_root / "HellsaizUpdater.exe").write_bytes(b"stable-updater")
    user_data = install_root / "user-data"
    user_data.mkdir()
    (user_data / "profile.json").write_text('{"theme":"dark"}', encoding="utf-8")
    (install_root / "active.json").write_text(
        json.dumps({"schema_version": 1, "active_version": "0.1.3", "previous_version": None}),
        encoding="utf-8",
    )

    payload = {
        "HellsaizPC_AI.exe": b"new-app",
        "_internal/Qt6Core.dll": b"qt-runtime",
    }
    records = {
        name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in payload.items()
    }
    manifest = {
        "schema_version": 1,
        "app_id": updater.APP_ID,
        "version": "0.1.4",
        "platform": updater.PLATFORM,
        "entrypoint": "HellsaizPC_AI.exe",
        "files": records,
    }

    update_dir = install_root / "updates" / "0.1.4"
    update_dir.mkdir(parents=True)
    archive_path = update_dir / "package.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, data in payload.items():
            archive.writestr(name, data)
    manifest_path = update_dir / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    signature_path = update_dir / "manifest.sig"
    signature_path.write_text("test-signature", encoding="ascii")

    monkeypatch.setattr(updater, "verify_signed_manifest", lambda *_args: manifest)
    monkeypatch.setattr(updater, "_wait_for_parent", lambda *_args: None)
    if health_state == "exception":
        def fail_launch(*_args):
            raise OSError("launcher failed to start")
        monkeypatch.setattr(updater, "_launch_and_check", fail_launch)
    else:
        monkeypatch.setattr(updater, "_launch_and_check", lambda *_args: health_state == "ok")

    if health_state == "ok":
        result = updater.apply_update(
            install_root, archive_path, manifest_path, signature_path,
            "full", "0.1.3", 0,
        )
        assert result == versions / "0.1.4"
        assert (result / "HellsaizPC_AI.exe").read_bytes() == b"new-app"
        assert (versions / "0.1.3" / "HellsaizPC_AI.exe").read_bytes() == b"old-app"
        assert json.loads((install_root / "active.json").read_text(encoding="utf-8"))["active_version"] == "0.1.4"
        assert (user_data / "profile.json").read_text(encoding="utf-8") == '{"theme":"dark"}'
        assert not update_dir.exists()
    else:
        with pytest.raises(ApplyUpdateError, match="автоматический откат|автоматический откат"):
            updater.apply_update(
                install_root, archive_path, manifest_path, signature_path,
                "full", "0.1.3", 0,
            )
        active = json.loads((install_root / "active.json").read_text(encoding="utf-8"))
        assert active["active_version"] == "0.1.3"
        assert (versions / "0.1.3" / "HellsaizPC_AI.exe").read_bytes() == b"old-app"
        assert not (versions / "0.1.4").exists()
        assert (user_data / "profile.json").is_file()

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from hellsaiz_pc_ai.update_client import UpdateCheckError


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "package_release.py"
_SPEC = importlib.util.spec_from_file_location("hellsaiz_package_release", _SCRIPT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Could not load scripts/package_release.py for tests.")
_PACKAGE_RELEASE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PACKAGE_RELEASE)

make_portable_zip = _PACKAGE_RELEASE.make_portable_zip
validate_portable_zip = _PACKAGE_RELEASE.validate_portable_zip


def _portable_layout(root: Path, version: str = "0.1.3") -> Path:
    version_dir = root / "versions" / version
    version_dir.mkdir(parents=True)
    (root / "HellsaizLauncher.exe").write_bytes(b"launcher")
    (root / "HellsaizUpdater.exe").write_bytes(b"updater")
    (version_dir / "HellsaizPC_AI.exe").write_bytes(b"desktop")
    (version_dir / "Qt6Core.dll").write_bytes(b"qt-runtime")
    (root / "active.json").write_text(
        json.dumps(
            {"schema_version": 1, "active_version": version, "previous_version": None}
        ),
        encoding="utf-8",
    )
    return root


def test_portable_zip_contains_bootstrap_and_active_application(tmp_path: Path):
    install_root = _portable_layout(tmp_path / "install")
    archive_path = tmp_path / "HellsaizPC_AI-windows-x64-portable.zip"

    make_portable_zip(install_root, archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())

    assert "active.json" in names
    assert "HellsaizLauncher.exe" in names
    assert "HellsaizUpdater.exe" in names
    assert "versions/0.1.3/HellsaizPC_AI.exe" in names
    assert "versions/0.1.3/Qt6Core.dll" in names
    validate_portable_zip(archive_path)


def test_portable_zip_rejects_invalid_active_version(tmp_path: Path):
    install_root = tmp_path / "install"
    _portable_layout(install_root)
    (install_root / "active.json").write_text(
        '{"schema_version":1,"active_version":"../outside"}',
        encoding="utf-8",
    )

    with pytest.raises(UpdateCheckError):
        make_portable_zip(install_root, tmp_path / "portable.zip")


def test_portable_zip_validation_rejects_missing_updater(tmp_path: Path):
    install_root = _portable_layout(tmp_path / "install")
    (install_root / "HellsaizUpdater.exe").unlink()
    archive_path = tmp_path / "invalid.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("active.json", json.dumps({"schema_version":1,"active_version":"0.1.3"}))
        archive.writestr("HellsaizLauncher.exe", b"launcher")

    with pytest.raises(ValueError, match="missing"):
        validate_portable_zip(archive_path)

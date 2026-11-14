from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.package_release import make_portable_zip, validate_portable_zip


def _install_tree(root: Path) -> tuple[str, list[str]]:
    version = "1.2.3"
    app_files = ["HellsaizPC_AI.exe", "_internal/Qt6Core.dll", "_internal/runtime.dat"]
    (root / "HellsaizLauncher.exe").write_bytes(b"launcher")
    (root / "HellsaizUpdater.exe").write_bytes(b"updater")
    (root / "active.json").write_text(
        json.dumps({"schema_version": 1, "active_version": version, "previous_version": None}),
        encoding="utf-8",
    )
    version_root = root / "versions" / version
    for relative in app_files:
        target = version_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative.encode())
    return version, app_files


def test_portable_zip_has_launcher_root_and_versioned_app(tmp_path: Path):
    install_root = tmp_path / "install"
    install_root.mkdir()
    version, files = _install_tree(install_root)
    package = tmp_path / "portable.zip"

    make_portable_zip(install_root, package, version, files)
    validate_portable_zip(package, version, files)

    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        assert "active.json" in names
        assert "HellsaizLauncher.exe" in names
        assert "HellsaizUpdater.exe" in names
        assert f"versions/{version}/HellsaizPC_AI.exe" in names
        assert "HellsaizPC_AI.exe" not in names


def test_portable_zip_rejects_files_outside_signed_manifest(tmp_path: Path):
    install_root = tmp_path / "install"
    install_root.mkdir()
    version, files = _install_tree(install_root)
    (install_root / "versions" / version / "unlisted.dll").write_bytes(b"unexpected")

    with pytest.raises(ValueError, match="do not match"):
        make_portable_zip(install_root, tmp_path / "portable.zip", version, files)


def test_portable_zip_validator_rejects_wrong_active_version(tmp_path: Path):
    install_root = tmp_path / "install"
    install_root.mkdir()
    version, files = _install_tree(install_root)
    package = tmp_path / "portable.zip"
    make_portable_zip(install_root, package, version, files)
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr("active.json", '{"schema_version":1,"active_version":"9.9.9"}')

    with pytest.raises(ValueError, match="contents"):
        validate_portable_zip(package, version, files)

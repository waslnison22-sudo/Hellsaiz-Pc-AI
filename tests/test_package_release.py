from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "package_release.py"
_SPEC = importlib.util.spec_from_file_location("hellsaiz_package_release", _SCRIPT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Could not load scripts/package_release.py for tests.")
_PACKAGE_RELEASE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PACKAGE_RELEASE)

make_portable_zip = _PACKAGE_RELEASE.make_portable_zip
validate_portable_zip = _PACKAGE_RELEASE.validate_portable_zip


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

    # Rewrite the archive with a tampered active_version instead of appending a
    # duplicate entry: duplicate zip names raise zipfile's UserWarning on every run.
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        payload = {name: archive.read(name) for name in names}
    payload["active.json"] = b'{"schema_version":1,"active_version":"9.9.9"}'
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, payload[name])

    with pytest.raises(ValueError, match="does not select the packaged version"):
        validate_portable_zip(package, version, files)

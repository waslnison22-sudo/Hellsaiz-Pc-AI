from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hellsaiz_pc_ai.update_client import APP_ID, PLATFORM, UpdateCheckError, verify_signed_manifest

PORTABLE_PACKAGE_NAME = "HellsaizPC_AI-windows-x64-portable.zip"
UPDATE_PACKAGE_NAME = "HellsaizPC_AI-windows-x64-full.zip"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files_manifest(app_dir: Path) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(app_dir.rglob("*")):
        if path.is_symlink():
            raise SystemExit(f"Symbolic links are not allowed in the release bundle: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(app_dir).as_posix()
        files[relative] = {"size": path.stat().st_size, "sha256": sha256_file(path)}
    if not files or "HellsaizPC_AI.exe" not in files:
        raise SystemExit("The PyInstaller onedir bundle is missing HellsaizPC_AI.exe.")
    return files


def make_zip(app_dir: Path, destination: Path, relative_files: list[str]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7, allowZip64=True
    ) as archive:
        for relative in relative_files:
            source = app_dir.joinpath(*PurePosixPath(relative).parts)
            archive.write(source, arcname=relative)
    temporary.replace(destination)


def make_portable_zip(
    install_root: Path, destination: Path, version: str, app_files: list[str]
) -> None:
    """Create the user-facing launcher layout; never use this ZIP for update extraction."""
    required = ("active.json", "HellsaizLauncher.exe", "HellsaizUpdater.exe")
    for name in required:
        if not (install_root / name).is_file():
            raise ValueError(f"Portable package is missing {name}.")
    version_root = install_root / "versions" / version
    if not version_root.is_dir():
        raise ValueError(f"Portable package is missing versions/{version}.")
    expected = {PurePosixPath(name).as_posix() for name in app_files}
    actual = {
        item.relative_to(version_root).as_posix()
        for item in version_root.rglob("*") if item.is_file()
    }
    if actual != expected:
        raise ValueError("Portable app files do not match the signed release manifest.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7, allowZip64=True
    ) as archive:
        for name in required:
            archive.write(install_root / name, arcname=name)
        for relative in sorted(expected):
            source = version_root.joinpath(*PurePosixPath(relative).parts)
            archive.write(source, arcname=f"versions/{version}/{relative}")
    temporary.replace(destination)


def validate_portable_zip(archive_path: Path, version: str, app_files: list[str]) -> None:
    expected = {"active.json", "HellsaizLauncher.exe", "HellsaizUpdater.exe"}
    expected.update(f"versions/{version}/{name}" for name in app_files)
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != expected:
            raise ValueError("Portable ZIP contents do not match the launcher layout and manifest.")
        active = json.loads(archive.read("active.json").decode("utf-8"))
        if active.get("schema_version") != 1 or active.get("active_version") != version:
            raise ValueError("Portable ZIP active.json does not select the packaged version.")
        if f"versions/{version}/HellsaizPC_AI.exe" not in expected:
            raise ValueError("Portable ZIP is missing the application entrypoint.")


def load_previous_manifest(manifest_path: Path, signature_path: Path) -> dict[str, Any]:
    try:
        raw = manifest_path.read_bytes()
        signature = signature_path.read_text(encoding="ascii")
        return verify_signed_manifest(raw, signature)
    except (OSError, UnicodeError, UpdateCheckError) as exc:
        raise SystemExit(f"Previous release manifest could not be trusted: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--updater", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--previous-manifest", type=Path)
    parser.add_argument("--previous-signature", type=Path)
    args = parser.parse_args()

    version = args.version.removeprefix("v")
    app_dir, launcher, updater, output = (
        args.app_dir.resolve(), args.launcher.resolve(), args.updater.resolve(), args.output.resolve()
    )
    if not app_dir.is_dir() or not launcher.is_file() or not updater.is_file():
        raise SystemExit("Build output is incomplete. Expected app, launcher and updater files.")

    signing_key_text = os.environ.get("HELLSAIZ_UPDATE_SIGNING_KEY", "").strip()
    if not signing_key_text:
        raise SystemExit(
            "HELLSAIZ_UPDATE_SIGNING_KEY is missing. Add the Ed25519 private key as a GitHub Actions secret."
        )
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(signing_key_text, validate=True)
        )
    except (ValueError, TypeError) as exc:
        raise SystemExit(
            "HELLSAIZ_UPDATE_SIGNING_KEY must be base64-encoded raw Ed25519 private key bytes."
        ) from exc

    files = files_manifest(app_dir)
    manifest = {
        "schema_version": 1,
        "app_id": APP_ID,
        "version": version,
        "platform": PLATFORM,
        "entrypoint": "HellsaizPC_AI.exe",
        "files": files,
    }
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    signature = base64.b64encode(private_key.sign(manifest_bytes)).decode("ascii")
    try:
        verify_signed_manifest(manifest_bytes, signature)
    except UpdateCheckError as exc:
        raise SystemExit(
            "The release signing key does not match the public key embedded in the application. "
            "Refusing to publish an update that installed clients cannot verify."
        ) from exc

    release_assets = output / "release-assets"
    release_assets.mkdir(parents=True, exist_ok=True)
    (release_assets / "HellsaizPC_AI-update-manifest.json").write_bytes(manifest_bytes)
    (release_assets / "HellsaizPC_AI-update-manifest.sig").write_text(
        signature + "\n", encoding="ascii"
    )

    # Internal update archives contain only manifest-listed files at ZIP root.
    make_zip(app_dir, release_assets / UPDATE_PACKAGE_NAME, sorted(files))

    install_root = output / "install"
    if install_root.exists():
        shutil.rmtree(install_root)
    version_dir = install_root / "versions" / version
    version_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_dir, version_dir)
    shutil.copy2(launcher, install_root / "HellsaizLauncher.exe")
    shutil.copy2(updater, install_root / "HellsaizUpdater.exe")
    (install_root / "active.json").write_text(
        json.dumps(
            {"schema_version": 1, "active_version": version, "previous_version": None},
            indent=2,
        ),
        encoding="utf-8",
    )

    portable_path = release_assets / PORTABLE_PACKAGE_NAME
    make_portable_zip(install_root, portable_path, version, sorted(files))
    validate_portable_zip(portable_path, version, sorted(files))

    if args.previous_manifest and args.previous_signature:
        previous = load_previous_manifest(args.previous_manifest, args.previous_signature)
        previous_version = previous["version"]
        previous_files = previous["files"]
        changed = [
            relative for relative, record in files.items()
            if previous_files.get(relative) != record
        ]
        if changed:
            delta_name = f"HellsaizPC_AI-windows-x64-delta-from-{previous_version}.zip"
            make_zip(app_dir, release_assets / delta_name, sorted(changed))
            print(f"Created delta package from {previous_version}: {len(changed)} changed files.")
        else:
            print(f"No binary files changed since {previous_version}; no delta archive was created.")

    total = sum(record["size"] for record in files.values())
    print(f"Release manifest signed for {version}; {len(files)} files, {total} bytes.")
    print(f"Portable package validated: {portable_path}")
    print(f"Internal update package: {release_assets / UPDATE_PACKAGE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

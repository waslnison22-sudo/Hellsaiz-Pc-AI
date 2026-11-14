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

from hellsaiz_pc_ai.update_client import (
    APP_ID,
    PLATFORM,
    UpdateCheckError,
    _safe_manifest_path,
    _version_parts,
    verify_signed_manifest,
)


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


def portable_file_list(install_root: Path) -> list[str]:
    """Return the validated root-relative files for a first-install portable bundle."""
    root = install_root.resolve()
    if install_root.is_symlink() or not root.is_dir():
        raise ValueError("Portable install root is missing or is a symbolic link.")

    active_path = root / "active.json"
    launcher_path = root / "HellsaizLauncher.exe"
    updater_path = root / "HellsaizUpdater.exe"
    for required in (active_path, launcher_path, updater_path):
        if required.is_symlink() or not required.is_file():
            raise ValueError(f"Portable bundle is missing a required file: {required.name}")

    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Portable bundle active.json is invalid.") from exc
    if not isinstance(active, dict) or active.get("schema_version") != 1:
        raise ValueError("Portable bundle active.json has an unsupported schema.")
    version = active.get("active_version")
    if not isinstance(version, str):
        raise ValueError("Portable bundle active.json has no active version.")
    _version_parts(version)

    versions_root = root / "versions"
    version_dir = versions_root / version
    if versions_root.is_symlink() or version_dir.is_symlink() or not version_dir.is_dir():
        raise ValueError("Portable bundle active version directory is missing or unsafe.")
    if not (version_dir / "HellsaizPC_AI.exe").is_file():
        raise ValueError("Portable bundle active version has no HellsaizPC_AI.exe.")

    files: list[str] = []
    seen: set[str] = set()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symbolic links are not allowed in the portable bundle: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        _safe_manifest_path(relative)
        folded = relative.casefold()
        if folded in seen:
            raise ValueError(f"Portable bundle contains duplicate paths: {relative}")
        seen.add(folded)
        files.append(relative)

    required_paths = {
        "active.json",
        "HellsaizLauncher.exe",
        "HellsaizUpdater.exe",
        f"versions/{version}/HellsaizPC_AI.exe",
    }
    if not required_paths.issubset(seen):
        raise ValueError("Portable bundle does not contain all required launcher files.")
    return files


def validate_portable_zip(archive_path: Path) -> None:
    """Validate that a portable ZIP can bootstrap the launcher and updater."""
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            if not names:
                raise ValueError("Portable ZIP is empty.")
            folded: set[str] = set()
            for name in names:
                _safe_manifest_path(name)
                if name.casefold() in folded:
                    raise ValueError(f"Portable ZIP contains duplicate paths: {name}")
                folded.add(name.casefold())

            required = {"active.json", "HellsaizLauncher.exe", "HellsaizUpdater.exe"}
            if not required.issubset(folded):
                raise ValueError("Portable ZIP is missing active.json, Launcher or Updater.")

            active = json.loads(archive.read("active.json").decode("utf-8"))
            if not isinstance(active, dict) or active.get("schema_version") != 1:
                raise ValueError("Portable ZIP active.json has an unsupported schema.")
            version = active.get("active_version")
            if not isinstance(version, str):
                raise ValueError("Portable ZIP active.json has no active version.")
            _version_parts(version)
            entrypoint = f"versions/{version}/HellsaizPC_AI.exe".casefold()
            if entrypoint not in folded:
                raise ValueError("Portable ZIP does not contain the active application entrypoint.")
    except (OSError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Portable ZIP is invalid: {exc}") from exc


def make_portable_zip(install_root: Path, destination: Path) -> None:
    files = portable_file_list(install_root)
    make_zip(install_root, destination, files)
    validate_portable_zip(destination)


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
    app_dir = args.app_dir.resolve()
    launcher = args.launcher.resolve()
    updater = args.updater.resolve()
    output = args.output.resolve()
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

    release_assets = output / "release-assets"
    release_assets.mkdir(parents=True, exist_ok=True)
    (release_assets / "HellsaizPC_AI-update-manifest.json").write_bytes(manifest_bytes)
    (release_assets / "HellsaizPC_AI-update-manifest.sig").write_text(
        signature + "\n", encoding="ascii"
    )

    make_zip(
        app_dir,
        release_assets / "HellsaizPC_AI-windows-x64-full.zip",
        sorted(files),
    )

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

    portable_archive = release_assets / "HellsaizPC_AI-windows-x64-portable.zip"
    make_portable_zip(install_root, portable_archive)

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
    print(f"Portable first-install ZIP prepared at {portable_archive}.")
    print(f"Internal updater ZIP prepared at {release_assets / 'HellsaizPC_AI-windows-x64-full.zip'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from hellsaiz_pc_ai.update_client import (
    APP_ID,
    MAX_TOTAL_FILE_BYTES,
    PLATFORM,
    UpdateCheckError,
    _safe_manifest_path,
    _validate_manifest,
    verify_signed_manifest,
)


class ApplyUpdateError(RuntimeError):
    pass


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _wait_for_parent(pid: int, timeout_seconds: int = 120) -> None:
    if pid <= 0 or os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    SYNCHRONIZE = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        # ERROR_INVALID_PARAMETER means the parent has already exited.
        if error == 87:
            return
        raise ApplyUpdateError(f"Не удалось дождаться закрытия приложения (Win32 {error}).")
    try:
        result = ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_seconds * 1000)
        if result != 0:
            raise ApplyUpdateError("Приложение не закрылось вовремя. Обновление отменено.")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _safe_destination(root: Path, relative: str) -> Path:
    safe = _safe_manifest_path(relative)
    destination = root.joinpath(*PurePosixPath(safe).parts)
    resolved = destination.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ApplyUpdateError(f"Путь выходит за пределы каталога версии: {relative}")
    return destination


def _clone_current_version(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise ApplyUpdateError("Текущая версия не найдена; delta-пакет применить нельзя.")
    destination.mkdir(parents=True, exist_ok=False)
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_symlink():
            raise ApplyUpdateError("В текущей версии обнаружена символическая ссылка.")
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(item, target)
            except OSError:
                shutil.copy2(item, target)


def _prune_to_manifest(stage: Path, manifest_files: dict[str, dict[str, Any]]) -> None:
    expected = {path.casefold() for path in manifest_files}
    for item in sorted(stage.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        relative = item.relative_to(stage).as_posix()
        if item.is_symlink():
            raise ApplyUpdateError("В папке версии обнаружена символическая ссылка.")
        if item.is_file() and relative.casefold() not in expected:
            item.unlink()
        elif item.is_dir():
            try:
                item.rmdir()
            except OSError:
                pass


def _extract_archive(archive_path: Path, stage: Path, mode: str, expected_files: dict[str, Any]) -> None:
    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ApplyUpdateError("ZIP-пакет обновления повреждён.") from exc

    seen: set[str] = set()
    total_size = 0
    with archive:
        entries = archive.infolist()
        if not entries or len(entries) > 10000:
            raise ApplyUpdateError("В ZIP-пакете недопустимое количество файлов.")
        for info in entries:
            if info.is_dir():
                continue
            relative = _safe_manifest_path(info.filename)
            folded = relative.casefold()
            if folded in seen:
                raise ApplyUpdateError("В ZIP-пакете есть дублирующиеся пути.")
            seen.add(folded)
            record = expected_files.get(relative)
            if record is None:
                raise ApplyUpdateError(f"ZIP-пакет содержит файл, которого нет в манифесте: {relative}")
            if info.file_size != record["size"]:
                raise ApplyUpdateError(f"Размер файла в ZIP не совпадает с манифестом: {relative}")
            total_size += info.file_size
            if total_size > MAX_TOTAL_FILE_BYTES:
                raise ApplyUpdateError("Распаковываемый пакет превышает допустимый размер.")
            # Reject symbolic links and other special Unix file types.
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            file_type = unix_mode & 0o170000
            if file_type not in {0, 0o100000}:
                raise ApplyUpdateError("ZIP-пакет содержит ссылку или специальный файл.")
            destination = _safe_destination(stage, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)

    if mode == "full" and seen != {path.casefold() for path in expected_files}:
        raise ApplyUpdateError("Полный пакет не содержит все файлы из манифеста.")


def _verify_payload(stage: Path, manifest_files: dict[str, dict[str, Any]]) -> None:
    actual: dict[str, Path] = {}
    for item in stage.rglob("*"):
        if item.is_symlink():
            raise ApplyUpdateError("В новой версии обнаружена символическая ссылка.")
        if item.is_file():
            actual[item.relative_to(stage).as_posix()] = item
    expected_case = {path.casefold() for path in manifest_files}
    actual_case = {path.casefold() for path in actual}
    if actual_case != expected_case:
        missing = sorted(expected_case - actual_case)
        extra = sorted(actual_case - expected_case)
        raise ApplyUpdateError(
            f"Набор файлов новой версии не совпал с манифестом. Отсутствуют: {missing[:5]}, лишние: {extra[:5]}"
        )
    for relative, record in manifest_files.items():
        matching = next(path for path in actual if path.casefold() == relative.casefold())
        file_path = actual[matching]
        if file_path.stat().st_size != record["size"]:
            raise ApplyUpdateError(f"Размер файла не прошёл проверку: {relative}")
        digest = hashlib.sha256()
        with file_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != record["sha256"]:
            raise ApplyUpdateError(f"SHA-256 файла не прошёл проверку: {relative}")


def _write_log(root: Path, message: str) -> None:
    try:
        log = root / "updates" / "updater.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def _launch_and_check(root: Path, version: str, timeout_seconds: int = 60) -> bool:
    launcher = root / "HellsaizLauncher.exe"
    if not launcher.is_file():
        raise ApplyUpdateError("Не найден стабильный HellsaizLauncher.exe.")
    marker = root / "health" / f"{version}.ok"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.unlink(missing_ok=True)
    process = subprocess.Popen([str(launcher)], cwd=str(root), close_fds=True)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if marker.is_file():
            return True
        if process.poll() is not None:
            time.sleep(0.25)
            if marker.is_file():
                return True
            # The launcher may exit after creating the app process, so keep waiting.
        time.sleep(0.5)
    return False


def apply_update(
    install_root: Path,
    archive_path: Path,
    manifest_path: Path,
    signature_path: Path,
    mode: str,
    from_version: str,
    parent_pid: int,
) -> Path:
    root = install_root.resolve()
    if os.name != "nt":
        raise ApplyUpdateError("Установка обновлений поддерживается только в Windows.")
    if mode not in {"full", "delta"}:
        raise ApplyUpdateError("Неизвестный режим пакета обновления.")
    for candidate in (archive_path, manifest_path, signature_path):
        resolved = candidate.resolve()
        if root not in resolved.parents:
            raise ApplyUpdateError("Временные файлы обновления должны находиться внутри install root.")

    try:
        manifest_bytes = manifest_path.read_bytes()
        signature_text = signature_path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise ApplyUpdateError(f"Не удалось прочитать манифест обновления: {exc}") from exc

    try:
        manifest = verify_signed_manifest(manifest_bytes, signature_text)
    except UpdateCheckError as exc:
        raise ApplyUpdateError(str(exc)) from exc
    manifest = _validate_manifest(manifest)
    if manifest.get("app_id") != APP_ID or manifest.get("platform") != PLATFORM:
        raise ApplyUpdateError("Манифест предназначен для другого приложения или платформы.")

    active_path = root / "active.json"
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
        active_version = str(active["active_version"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ApplyUpdateError("Не удалось определить текущую установленную версию.") from exc
    if active_version != from_version:
        raise ApplyUpdateError("Текущая версия приложения изменилась. Повторите проверку обновлений.")
    if manifest["version"] == active_version:
        raise ApplyUpdateError("Эта версия уже установлена.")

    _wait_for_parent(parent_pid)
    versions_root = root / "versions"
    current_dir = versions_root / active_version
    target_dir = versions_root / manifest["version"]
    stage = versions_root / f".staging-{manifest['version']}-{uuid.uuid4().hex}"
    versions_root.mkdir(parents=True, exist_ok=True)

    try:
        if mode == "delta":
            _clone_current_version(current_dir, stage)
            _prune_to_manifest(stage, manifest["files"])
        else:
            stage.mkdir(parents=True, exist_ok=False)

        _extract_archive(archive_path, stage, mode, manifest["files"])
        _verify_payload(stage, manifest["files"])

        if target_dir.exists():
            shutil.rmtree(target_dir)
        os.replace(stage, target_dir)

        previous = active_version
        _write_json_atomic(
            active_path,
            {
                "schema_version": 1,
                "active_version": manifest["version"],
                "previous_version": previous,
            },
        )
        _write_log(root, f"Activated version {manifest['version']} from {previous} ({mode}).")

        if not _launch_and_check(root, manifest["version"]):
            _write_json_atomic(
                active_path,
                {
                    "schema_version": 1,
                    "active_version": previous,
                    "previous_version": manifest["version"],
                },
            )
            _write_log(root, f"Health check failed for {manifest['version']}; rolled back to {previous}.")
            raise ApplyUpdateError(
                "Новая версия не прошла проверку запуска. Выполнен автоматический откат."
            )

        # Retain the active and immediately previous versions for rollback.
        keep = {manifest["version"], previous}
        for folder in versions_root.iterdir():
            if folder.is_dir() and not folder.name.startswith(".staging-") and folder.name not in keep:
                shutil.rmtree(folder, ignore_errors=True)
        try:
            update_dir = archive_path.parent
            if update_dir.parent == (root / "updates"):
                shutil.rmtree(update_dir, ignore_errors=True)
        except OSError:
            pass
        _write_log(root, f"Update to {manifest['version']} completed.")
        return target_dir
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _show_error(message: str) -> None:
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Hellsaiz PC AI — обновление", 0x10)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hellsaiz PC AI update helper")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--mode", choices=("full", "delta"), required=True)
    parser.add_argument("--from-version", required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args()

    try:
        if not args.install:
            raise ApplyUpdateError("Не указан режим установки обновления.")
        apply_update(
            args.install_root, args.archive, args.manifest, args.signature,
            args.mode, args.from_version, args.parent_pid
        )
        return 0
    except (ApplyUpdateError, UpdateCheckError, OSError, ValueError, zipfile.BadZipFile) as exc:
        _write_log(args.install_root, f"Update failed: {exc}")
        _show_error(f"Обновление не установлено. Текущая версия сохранена.\n\n{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

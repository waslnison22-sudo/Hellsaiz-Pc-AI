from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_REPOSITORY = "waslnison22-sudo/Hellsaiz-Pc-AI"
APP_ID = "hellsaiz-pc-ai"
PLATFORM = "win-x64"
MANIFEST_ASSET = "HellsaizPC_AI-update-manifest.json"
SIGNATURE_ASSET = "HellsaizPC_AI-update-manifest.sig"
FULL_PACKAGE_ASSET = "HellsaizPC_AI-windows-x64-full.zip"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_SIGNATURE_BYTES = 4096
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_TOTAL_FILE_BYTES = 3 * 1024 * 1024 * 1024
MAX_FILES = 10000


class UpdateCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedUpdate:
    version: str
    mode: str
    from_version: str
    archive_path: Path
    manifest_path: Path
    signature_path: Path
    package_sha256: str


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    update_available: bool
    release_url: str
    published_at: str
    notes: str
    manifest: dict[str, Any]
    manifest_bytes: bytes
    signature_text: str
    package_asset_id: int | None
    package_asset_name: str | None
    package_asset_size: int
    package_mode: str | None
    package_sha256: str | None


def _version_parts(value: str) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", value.strip())
    if not match:
        raise UpdateCheckError(f"Не удалось разобрать номер версии: {value}")
    prerelease = match.group(4)
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        0 if prerelease else 1,
    )


def _request_bytes(
    url: str,
    token: str,
    accept: str,
    timeout_seconds: float,
    max_bytes: int,
) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise UpdateCheckError("Запрос обновления направлен не на api.github.com.")
    headers = {
        "Accept": accept,
        "User-Agent": "Hellsaiz-PC-AI-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    request = urllib.request.Request(url, headers=headers)
    no_redirect = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _NoRedirect(),
    )
    try:
        response = no_redirect.open(request, timeout=timeout_seconds)
        with response:
            raw = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        if exc.code not in {301, 302, 303, 307, 308}:
            raise _http_error(exc) from exc
        location = exc.headers.get("Location")
        if not location:
            raise UpdateCheckError("GitHub вернул перенаправление без адреса загрузки.") from exc
        redirected = urllib.parse.urlparse(location)
        allowed_hosts = {
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        }
        if redirected.scheme != "https" or redirected.hostname not in allowed_hosts:
            raise UpdateCheckError("GitHub перенаправил загрузку на недоверенный сервер.") from exc
        # The GitHub bearer token is deliberately not forwarded to the asset host.
        redirected_request = urllib.request.Request(
            location,
            headers={"User-Agent": "Hellsaiz-PC-AI-Updater", "Accept": "application/octet-stream"},
        )
        try:
            with urllib.request.urlopen(
                redirected_request, timeout=timeout_seconds, context=ssl.create_default_context()
            ) as response:
                raw = response.read(max_bytes + 1)
        except (urllib.error.URLError, TimeoutError, urllib.error.HTTPError) as redirect_error:
            raise UpdateCheckError(f"Не удалось загрузить файл релиза: {redirect_error}") from redirect_error
    except (urllib.error.URLError, TimeoutError) as exc:
        raise UpdateCheckError(f"Не удалось подключиться к GitHub: {exc}") from exc
    if len(raw) > max_bytes:
        raise UpdateCheckError("Размер файла обновления превышает допустимый предел.")
    return raw


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_error(exc: urllib.error.HTTPError) -> UpdateCheckError:
    if exc.code == 404:
        return UpdateCheckError(
            "Релиз не найден или репозиторий приватный. Для приватного канала нужен ключ GitHub с правом Contents: read."
        )
    if exc.code in {401, 403}:
        return UpdateCheckError("GitHub не принял ключ доступа. Проверь его права Contents: read.")
    return UpdateCheckError(f"GitHub вернул HTTP {exc.code}.")


def _safe_manifest_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 240:
        raise UpdateCheckError("Манифест содержит некорректный путь.")
    if "\\" in value or ":" in value or value.startswith("/"):
        raise UpdateCheckError(f"Недопустимый путь в манифесте: {value}")
    pure = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise UpdateCheckError(f"Недопустимый путь в манифесте: {value}")
    if not pure.parts:
        raise UpdateCheckError("Пустой путь в манифесте.")
    for part in pure.parts:
        if part.endswith((" ", ".")) or part.casefold() in {
            "con", "prn", "aux", "nul",
            *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10)),
        }:
            raise UpdateCheckError(f"Недопустимое имя файла в манифесте: {value}")
    return pure.as_posix()


def _validate_manifest(manifest: Any, expected_version: str | None = None) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise UpdateCheckError("Манифест обновления имеет неверный формат.")
    if manifest.get("schema_version") != 1 or manifest.get("app_id") != APP_ID:
        raise UpdateCheckError("Манифест не предназначен для Hellsaiz PC AI.")
    if manifest.get("platform") != PLATFORM:
        raise UpdateCheckError("Этот пакет не предназначен для Windows x64.")
    version = manifest.get("version")
    if not isinstance(version, str):
        raise UpdateCheckError("В манифесте отсутствует версия.")
    _version_parts(version)
    if expected_version and _version_parts(version) != _version_parts(expected_version):
        raise UpdateCheckError("Версия манифеста не совпадает с версией релиза.")
    entrypoint = _safe_manifest_path(manifest.get("entrypoint", ""))
    files = manifest.get("files")
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        raise UpdateCheckError("Манифест не содержит корректный список файлов.")
    normalized: dict[str, dict[str, Any]] = {}
    total_size = 0
    for raw_path, record in files.items():
        path = _safe_manifest_path(raw_path)
        if path.casefold() in {key.casefold() for key in normalized}:
            raise UpdateCheckError("В манифесте есть пути, конфликтующие без учёта регистра.")
        if not isinstance(record, dict):
            raise UpdateCheckError(f"Некорректная запись файла: {path}")
        size = record.get("size")
        digest = record.get("sha256")
        if (
            not isinstance(size, int) or isinstance(size, bool) or size < 0
            or size > MAX_TOTAL_FILE_BYTES
            or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
        ):
            raise UpdateCheckError(f"Некорректный размер или SHA-256 файла: {path}")
        total_size += size
        if total_size > MAX_TOTAL_FILE_BYTES:
            raise UpdateCheckError("Общий размер файлов в манифесте слишком велик.")
        normalized[path] = {"size": size, "sha256": digest}
    if entrypoint not in normalized:
        raise UpdateCheckError("Исполняемый файл отсутствует в манифесте.")
    manifest = dict(manifest)
    manifest["entrypoint"] = entrypoint
    manifest["files"] = normalized
    return manifest


def verify_signed_manifest(manifest_bytes: bytes, signature_text: str) -> dict[str, Any]:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from hellsaiz_pc_ai.update_trust import UPDATE_PUBLIC_KEY_B64
    except ImportError as exc:
        raise UpdateCheckError("Не найден модуль криптографической проверки обновлений.") from exc

    try:
        signature = base64.b64decode(signature_text.strip(), validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(UPDATE_PUBLIC_KEY_B64))
        public_key.verify(signature, manifest_bytes)
    except (ValueError, InvalidSignature) as exc:
        raise UpdateCheckError("Подпись манифеста обновления недействительна.") from exc

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError("Манифест обновления повреждён.") from exc
    return _validate_manifest(manifest)


def _asset_map(release: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise UpdateCheckError("GitHub вернул некорректный список файлов релиза.")
    mapped: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        asset_id = asset.get("id")
        if isinstance(name, str) and isinstance(asset_id, int):
            mapped[name] = asset
    return mapped


def check_latest_release(
    current_version: str,
    access_token: str = "",
    repository: str = DEFAULT_REPOSITORY,
    timeout_seconds: float = 15.0,
) -> UpdateInfo:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise UpdateCheckError("Неверно указан репозиторий обновлений.")
    url = f"https://api.github.com/repos/{repository}/releases/latest"
    raw_release = _request_bytes(
        url, access_token, "application/vnd.github+json", timeout_seconds, 4 * 1024 * 1024
    )
    try:
        release = json.loads(raw_release.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError("GitHub вернул некорректное описание релиза.") from exc
    if not isinstance(release, dict):
        raise UpdateCheckError("GitHub вернул некорректное описание релиза.")

    tag = str(release.get("tag_name", "")).strip()
    if not tag:
        raise UpdateCheckError("В релизе отсутствует tag_name.")
    current = _version_parts(current_version)
    latest = _version_parts(tag)
    available = latest > current
    assets = _asset_map(release)

    if not available:
        return UpdateInfo(
            current_version, tag, False, str(release.get("html_url") or ""),
            str(release.get("published_at") or ""), str(release.get("body") or "")[:12000],
            {}, b"", "", None, None, 0, None, None,
        )

    manifest_asset = assets.get(MANIFEST_ASSET)
    signature_asset = assets.get(SIGNATURE_ASSET)
    if not manifest_asset or not signature_asset:
        raise UpdateCheckError("Релиз не содержит подписанный update-манифест.")
    manifest_bytes = _request_bytes(
        f"https://api.github.com/repos/{repository}/releases/assets/{manifest_asset['id']}",
        access_token, "application/octet-stream", timeout_seconds, MAX_MANIFEST_BYTES
    )
    signature_bytes = _request_bytes(
        f"https://api.github.com/repos/{repository}/releases/assets/{signature_asset['id']}",
        access_token, "application/octet-stream", timeout_seconds, MAX_SIGNATURE_BYTES
    )
    try:
        signature_text = signature_bytes.decode("ascii").strip()
    except UnicodeError as exc:
        raise UpdateCheckError("Подпись манифеста имеет неверный формат.") from exc

    manifest = verify_signed_manifest(manifest_bytes, signature_text)
    if _version_parts(manifest["version"]) != latest:
        raise UpdateCheckError("Версия манифеста не совпадает с тегом GitHub Release.")

    delta_name = f"HellsaizPC_AI-windows-x64-delta-from-{current_version}.zip"
    package = assets.get(delta_name)
    package_mode = "delta" if package else "full"
    if package is None:
        package = assets.get(FULL_PACKAGE_ASSET)
    if package is None:
        raise UpdateCheckError("В релизе отсутствует полный Windows x64 пакет.")
    package_size = int(package.get("size") or 0)
    if package_size <= 0 or package_size > MAX_PACKAGE_BYTES:
        raise UpdateCheckError("Размер пакета обновления некорректен.")
    digest_text = str(package.get("digest") or "")
    expected_sha = digest_text.removeprefix("sha256:").lower() if digest_text.startswith("sha256:") else None
    if expected_sha is not None and not re.fullmatch(r"[a-f0-9]{64}", expected_sha):
        expected_sha = None

    return UpdateInfo(
        current_version=current_version,
        latest_version=tag,
        update_available=True,
        release_url=str(release.get("html_url") or ""),
        published_at=str(release.get("published_at") or ""),
        notes=str(release.get("body") or "")[:12000],
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        signature_text=signature_text,
        package_asset_id=int(package["id"]),
        package_asset_name=str(package["name"]),
        package_asset_size=package_size,
        package_mode=package_mode,
        package_sha256=expected_sha,
    )


def download_update(
    info: UpdateInfo,
    access_token: str,
    install_root: Path,
    repository: str = DEFAULT_REPOSITORY,
    timeout_seconds: float = 60.0,
) -> PreparedUpdate:
    if not info.update_available or not info.package_asset_id or not info.package_mode:
        raise UpdateCheckError("Нет проверенного пакета для установки.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise UpdateCheckError("Неверно указан репозиторий обновлений.")

    update_dir = (install_root / "updates" / info.latest_version).resolve()
    updates_root = (install_root / "updates").resolve()
    if update_dir.parent != updates_root:
        raise UpdateCheckError("Папка обновления выходит за пределы install root.")
    update_dir.mkdir(parents=True, exist_ok=True)
    archive_path = update_dir / "package.zip"
    partial_path = update_dir / "package.zip.partial"
    manifest_path = update_dir / "manifest.json"
    signature_path = update_dir / "manifest.sig"

    raw = _request_bytes(
        f"https://api.github.com/repos/{repository}/releases/assets/{info.package_asset_id}",
        access_token,
        "application/octet-stream",
        timeout_seconds,
        MAX_PACKAGE_BYTES,
    )
    if info.package_sha256 and hashlib.sha256(raw).hexdigest() != info.package_sha256:
        raise UpdateCheckError("SHA-256 загруженного ZIP не совпадает с GitHub Release.")
    partial_path.write_bytes(raw)
    os.replace(partial_path, archive_path)
    manifest_path.write_bytes(info.manifest_bytes)
    signature_path.write_text(info.signature_text, encoding="ascii")

    return PreparedUpdate(
        version=info.latest_version,
        mode=str(info.package_mode),
        from_version=info.current_version,
        archive_path=archive_path,
        manifest_path=manifest_path,
        signature_path=signature_path,
        package_sha256=hashlib.sha256(raw).hexdigest(),
    )

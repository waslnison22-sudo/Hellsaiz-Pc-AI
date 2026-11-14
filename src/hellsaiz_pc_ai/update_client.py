from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass


DEFAULT_REPOSITORY = "waslnison22-sudo/Hellsaiz-Pc-AI"


class UpdateCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    update_available: bool
    release_url: str
    published_at: str
    notes: str
    package_url: str | None
    package_name: str | None
    package_sha256: str | None


def _version_parts(value: str) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+](\w+))?", value.strip(), re.IGNORECASE)
    if not match:
        raise UpdateCheckError(f"Не удалось разобрать номер версии: {value}")
    suffix = match.group(4)
    prerelease = 0 if suffix else 1
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease


def check_latest_release(
    current_version: str,
    access_token: str = "",
    repository: str = DEFAULT_REPOSITORY,
    timeout_seconds: float = 12.0,
) -> UpdateInfo:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise UpdateCheckError("Неверно указан репозиторий обновлений.")
    url = f"https://api.github.com/repos/{repository}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Hellsaiz-PC-AI-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if access_token.strip():
        headers["Authorization"] = f"Bearer {access_token.strip()}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateCheckError("Пока нет опубликованного стабильного релиза.") from exc
        if exc.code in {401, 403}:
            raise UpdateCheckError("GitHub не принял ключ доступа к каналу обновлений.") from exc
        raise UpdateCheckError(f"GitHub вернул HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeError) as exc:
        raise UpdateCheckError(f"Не удалось проверить обновления: {exc}") from exc

    if not isinstance(payload, dict):
        raise UpdateCheckError("Сервер обновлений вернул неверный формат.")
    latest = str(payload.get("tag_name", "")).strip()
    if not latest:
        raise UpdateCheckError("В релизе отсутствует tag_name.")
    available = _version_parts(latest) > _version_parts(current_version)

    package_url = None
    package_name = None
    package_sha256 = None
    assets = payload.get("assets", [])
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", ""))
            lowered = name.casefold()
            if "windows" not in lowered or not lowered.endswith(".zip"):
                continue
            digest = str(asset.get("digest") or "")
            if digest.startswith("sha256:"):
                package_sha256 = digest.removeprefix("sha256:").lower()
            package_url = str(asset.get("browser_download_url") or "") or None
            package_name = name
            break

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest,
        update_available=available,
        release_url=str(payload.get("html_url") or ""),
        published_at=str(payload.get("published_at") or ""),
        notes=str(payload.get("body") or "")[:12000],
        package_url=package_url,
        package_name=package_name,
        package_sha256=package_sha256,
    )

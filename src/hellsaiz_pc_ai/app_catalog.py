from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SHELL_LINK_MARKER = "__shell_link__"


@dataclass(frozen=True)
class AppCandidate:
    name: str
    path: Path
    launch_kind: str = "exe"

    @property
    def command(self) -> tuple[str, ...]:
        if self.launch_kind == "shortcut":
            return (SHELL_LINK_MARKER, str(self.path))
        return (str(self.path),)

    @property
    def key(self) -> str:
        stem = re.sub(r"[^a-z0-9]+", "-", self.name.casefold()).strip("-")
        if not stem:
            stem = re.sub(r"[^a-z0-9]+", "-", self.path.stem.casefold()).strip("-")
        return stem or "application"


def _existing_file(value: str | Path) -> Path | None:
    try:
        path = Path(value).expanduser()
        return path.resolve() if path.is_file() else None
    except (OSError, RuntimeError, ValueError):
        return None


def _extract_executable(display_icon: str) -> Path | None:
    value = display_icon.strip()
    if not value:
        return None
    quoted = re.match(r'^"([^"]+)"', value)
    if quoted:
        candidate = quoted.group(1)
    else:
        match = re.match(r"^(.+?\.exe)(?:,.*)?$", value, flags=re.IGNORECASE)
        if not match:
            return None
        candidate = match.group(1).strip().strip('"')
    return _existing_file(candidate)


def _registry_candidates() -> list[AppCandidate]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    result: list[AppCandidate] = []
    uninstall_root = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    app_paths_root = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    hives = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    views = (
        getattr(winreg, "KEY_WOW64_64KEY", 0),
        getattr(winreg, "KEY_WOW64_32KEY", 0),
    )

    for hive in hives:
        for view in views:
            access = winreg.KEY_READ | view
            try:
                root = winreg.OpenKey(hive, uninstall_root, 0, access)
            except OSError:
                root = None
            if root is not None:
                with root:
                    index = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(root, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            with winreg.OpenKey(root, subkey_name, 0, access) as subkey:
                                name = str(winreg.QueryValueEx(subkey, "DisplayName")[0]).strip()
                                icon = str(winreg.QueryValueEx(subkey, "DisplayIcon")[0])
                        except OSError:
                            continue
                        executable = _extract_executable(icon)
                        if name and executable:
                            result.append(AppCandidate(name, executable))

            try:
                root = winreg.OpenKey(hive, app_paths_root, 0, access)
            except OSError:
                root = None
            if root is not None:
                with root:
                    index = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(root, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            with winreg.OpenKey(root, subkey_name, 0, access) as subkey:
                                raw_path = str(winreg.QueryValueEx(subkey, None)[0])
                        except OSError:
                            continue
                        executable = _existing_file(raw_path)
                        if executable:
                            result.append(AppCandidate(Path(subkey_name).stem, executable))
    return result


def discover_windows_apps() -> list[AppCandidate]:
    """Discover Start-menu shortcuts and registry-registered executables.

    This intentionally avoids a recursive scan of every drive. Portable apps can
    be added with the file picker in the desktop UI.
    """
    if os.name != "nt":
        return []

    candidates: list[AppCandidate] = []
    local = os.environ.get("APPDATA")
    common = os.environ.get("PROGRAMDATA")
    roots: list[Path] = []
    if local:
        roots.append(Path(local) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if common:
        roots.append(Path(common) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    for root in roots:
        if not root.is_dir():
            continue
        try:
            for shortcut in root.rglob("*.lnk"):
                if shortcut.is_file():
                    candidates.append(AppCandidate(shortcut.stem, shortcut.resolve(), "shortcut"))
        except OSError:
            continue

    candidates.extend(_registry_candidates())
    unique: dict[tuple[str, str], AppCandidate] = {}
    for candidate in candidates:
        key = (candidate.launch_kind, str(candidate.path).casefold())
        unique.setdefault(key, candidate)
    return sorted(unique.values(), key=lambda item: item.name.casefold())


def load_user_catalog(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Не удалось прочитать каталог приложений: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Неподдерживаемый формат каталога приложений.")
    items = payload.get("applications", [])
    if not isinstance(items, list):
        raise ValueError("Поле applications должно быть списком.")
    valid: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key, name, raw_path = item.get("key"), item.get("name"), item.get("path")
        kind = item.get("launch_kind", "exe")
        aliases = item.get("aliases", [])
        if (
            not isinstance(key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", key)
            or not isinstance(name, str) or not name.strip()
            or not isinstance(raw_path, str) or kind not in {"exe", "shortcut"}
            or not isinstance(aliases, list)
            or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
        ):
            continue
        valid.append({
            "key": key,
            "name": name.strip(),
            "path": raw_path,
            "launch_kind": kind,
            "aliases": list(dict.fromkeys(alias.strip() for alias in aliases))[:64],
        })
    return valid


def save_user_catalog(path: Path, applications: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "applications": applications}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def add_candidate(
    path: Path,
    candidate: AppCandidate,
    existing: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if candidate.launch_kind not in {"exe", "shortcut"}:
        raise ValueError("Неподдерживаемый тип приложения.")
    resolved = _existing_file(candidate.path)
    if resolved is None:
        raise ValueError("Файл приложения больше не существует.")
    if candidate.launch_kind == "exe" and resolved.suffix.casefold() != ".exe":
        raise ValueError("Для обычного приложения выбери файл .exe.")
    if candidate.launch_kind == "shortcut" and resolved.suffix.casefold() != ".lnk":
        raise ValueError("Для ярлыка Windows выбери файл .lnk.")

    applications = list(existing if existing is not None else load_user_catalog(path))
    resolved_text = str(resolved)
    for item in applications:
        if str(item.get("path", "")).casefold() == resolved_text.casefold():
            return item

    base_key = candidate.key
    used = {str(item.get("key", "")) for item in applications}
    key = base_key
    suffix = 2
    while key in used:
        key = f"{base_key}-{suffix}"
        suffix += 1

    aliases = list(dict.fromkeys((candidate.name.strip(), resolved.stem)))
    entry = {
        "key": key,
        "name": candidate.name.strip(),
        "path": resolved_text,
        "launch_kind": candidate.launch_kind,
        "aliases": aliases,
    }
    applications.append(entry)
    save_user_catalog(path, applications)
    return entry


def catalog_mappings(
    applications: list[dict[str, Any]],
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    allowed: dict[str, tuple[str, ...]] = {}
    aliases: dict[str, tuple[str, ...]] = {}
    owners: dict[str, str] = {}
    for item in applications:
        key = item["key"].casefold()
        path = str(item["path"])
        kind = item.get("launch_kind", "exe")
        command = (SHELL_LINK_MARKER, path) if kind == "shortcut" else (path,)
        allowed[key] = command
        unique_aliases: list[str] = []
        for alias in item.get("aliases", []):
            normalized = re.sub(r"\s+", " ", str(alias).casefold()).strip()
            owner = owners.get(normalized)
            if normalized and (owner is None or owner == key):
                owners[normalized] = key
                unique_aliases.append(str(alias))
        aliases[key] = tuple(unique_aliases)
    return allowed, aliases

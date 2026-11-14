from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path


SUPPORTED_WALLPAPER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
MAX_WALLPAPER_BYTES = 100 * 1024 * 1024


class WallpaperError(ValueError):
    """Raised when a wallpaper cannot be safely imported or loaded."""


def _looks_like_image(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            header = stream.read(16)
    except OSError:
        return False
    return (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
        or header.startswith((b"GIF87a", b"GIF89a"))
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
        or header.startswith(b"BM")
    )


class WallpaperStore:
    """Private local wallpaper library. Empty state means a pure black background."""

    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "wallpapers"
        self.preferences_path = data_dir / "wallpaper.json"

    def active_wallpaper(self) -> Path | None:
        if not self.preferences_path.is_file() or self.preferences_path.is_symlink():
            return None
        try:
            data = json.loads(self.preferences_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        filename = data.get("filename") if isinstance(data, dict) else None
        if not isinstance(filename, str) or Path(filename).name != filename:
            return None
        path = self.directory / filename
        if (
            path.suffix.casefold() not in SUPPORTED_WALLPAPER_SUFFIXES
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > MAX_WALLPAPER_BYTES
            or not _looks_like_image(path)
        ):
            return None
        return path

    def import_wallpaper(self, source: Path) -> Path:
        if source.is_symlink() or not source.is_file():
            raise WallpaperError("Выбери обычный файл изображения, а не ссылку.")
        suffix = source.suffix.casefold()
        if suffix not in SUPPORTED_WALLPAPER_SUFFIXES:
            raise WallpaperError("Поддерживаются PNG, JPG, WEBP, BMP и GIF.")
        size = source.stat().st_size
        if size <= 0 or size > MAX_WALLPAPER_BYTES:
            raise WallpaperError("Размер обоев должен быть от 1 байта до 100 МБ.")
        if not _looks_like_image(source):
            raise WallpaperError("Файл не распознан как поддерживаемое изображение.")

        self.directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{suffix}"
        destination = self.directory / filename
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            with source.open("rb") as src, temporary.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
            if temporary.stat().st_size != size:
                raise WallpaperError("Файл обоев скопирован не полностью.")
            temporary.replace(destination)
            self._save({"filename": filename})
        except Exception:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise
        return destination

    def clear(self) -> None:
        self._save({"filename": None})

    def _save(self, value: dict[str, str | None]) -> None:
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.preferences_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.preferences_path)

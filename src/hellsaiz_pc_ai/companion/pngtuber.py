"""PNGTuber companion packs: strict ZIP import, registry and a frame renderer.

The owner's packs ship four 1024x1024 transparent PNG frames:
`idle.png`, `talking.png`, `blink.png`, `blink-talking.png` (plus optional docs).
Import validates the archive, extracts it under `companion_models/<slug>/` and
writes a `model.json` manifest in the format the existing `model_manifest`
module already understands.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap

from hellsaiz_pc_ai.companion.contracts import CompanionMode, CompanionSnapshot

FRAME_NAMES = ("idle.png", "talking.png", "blink.png", "blink-talking.png")
FRAME_STATES = {
    "idle.png": "idle",
    "talking.png": "talk",
    "blink.png": "blink",
    "blink-talking.png": "blink_talk",
}
ALLOWED_EXTENSIONS = {".png"}
ALLOWED_DOC_EXTENSIONS = {".txt", ".md", ".json"}
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
MAX_FILES = 64
SLUG_RE = re.compile(r"[^a-z0-9._-]+")


class ModelImportError(RuntimeError):
    """A human readable import failure (shown in the UI as-is)."""


def slugify(name: str) -> str:
    slug = SLUG_RE.sub("-", name.strip().casefold()).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug or not slug[0].isalnum():
        slug = f"model-{slug}" if slug else "model"
    return slug[:48]


@dataclass(frozen=True)
class PackagePlan:
    root: str
    frames: dict[str, str]
    docs: dict[str, str]
    model_meta: dict[str, Any]

    @property
    def slug(self) -> str:
        return slugify(self.model_meta.get("name") or self.root or "model")


def _normalise_entry(name: str) -> PurePosixPath:
    if "\\" in name or "\x00" in name:
        raise ModelImportError("Архив содержит недопустимый путь.")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ModelImportError("Архив содержит путь за пределами модели.")
    if path.parts and ":" in path.parts[0]:
        raise ModelImportError("Архив содержит путь с диском.")
    return path


def inspect_package(archive_path: Path) -> PackagePlan:
    """Validate the ZIP and describe what will be extracted."""
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise ModelImportError("Файл модели не найден.")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if not infos:
                raise ModelImportError("Архив пуст.")
            if len(infos) > MAX_FILES:
                raise ModelImportError("В архиве слишком много файлов.")
            total = sum(info.file_size for info in infos)
            if total > MAX_UNPACKED_BYTES:
                raise ModelImportError("Модель больше 200 МБ в распакованном виде.")
            roots: set[str] = set()
            frames: dict[str, str] = {}
            docs: dict[str, str] = {}
            for info in infos:
                path = _normalise_entry(info.filename)
                suffix = path.suffix.casefold()
                if suffix not in ALLOWED_EXTENSIONS | ALLOWED_DOC_EXTENSIONS:
                    raise ModelImportError(
                        f"В архиве есть недопустимый файл: {path.name}. "
                        "Разрешены только PNG и необязательный model.json."
                    )
                target = path.name.casefold()
                if suffix == ".png" or target == "model.json":
                    # Only payload files define the package root; a stray
                    # README next to the folder must not reject the pack.
                    roots.add(path.parts[0] if len(path.parts) > 1 else "")
                if suffix == ".png":
                    if target in FRAME_NAMES:
                        frames[target] = path.as_posix()
                    else:
                        # extra frames are allowed but not part of the state map
                        docs.setdefault(target, path.as_posix())
                else:
                    docs[target] = path.as_posix()
            if len(roots) > 1:
                raise ModelImportError(
                    "Архив должен содержать одну папку модели или файлы в корне."
                )
            if "idle.png" not in frames:
                raise ModelImportError(
                    "В архиве нет обязательного кадра idle.png — модель отклонена."
                )
            model_meta: dict[str, Any] = {}
            if "model.json" in docs:
                try:
                    raw = archive.read(docs["model.json"]).decode("utf-8")
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        model_meta = parsed
                except (UnicodeDecodeError, json.JSONDecodeError):
                    model_meta = {}
            return PackagePlan(
                root=next(iter(roots), ""),
                frames=frames,
                docs=docs,
                model_meta=model_meta,
            )
    except zipfile.BadZipFile as exc:
        raise ModelImportError("Файл не является корректным ZIP-архивом.") from exc


def _manifest_for(plan: PackagePlan, slug: str) -> dict[str, Any]:
    states = {
        state: Path(plan.frames[name]).name
        for name, state in FRAME_STATES.items()
        if name in plan.frames
    }
    return {
        "schema_version": 1,
        "model_id": slug,
        "display_name": str(plan.model_meta.get("name") or plan.root or slug)[:80],
        "format_id": "sprite",
        "renderer_id": "pngtuber",
        "entrypoint": Path(plan.frames["idle.png"]).name,
        "states": states,
        "author": str(plan.model_meta.get("author") or "")[:120],
        "description": str(plan.model_meta.get("description") or "")[:240],
        "added_at": int(time.time()),
    }


def import_pngtuber_zip(archive_path: Path, models_root: Path) -> Path:
    """Validate, extract and register a PNGTuber pack; returns its folder."""
    plan = inspect_package(archive_path)
    models_root = Path(models_root).expanduser()
    models_root.mkdir(parents=True, exist_ok=True)
    slug = plan.slug
    destination = models_root / slug
    staging = models_root / f".{slug}.import"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for name in list(plan.frames.values()) + list(plan.docs.values()):
                info = archive.getinfo(name)
                target = staging / Path(name).name
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        (staging / "model.json").write_text(
            json.dumps(_manifest_for(plan, slug), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except (OSError, KeyError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise ModelImportError(f"Не удалось распаковать модель: {exc}") from exc
    if destination.exists():
        shutil.rmtree(destination, ignore_errors=True)
    staging.replace(destination)
    return destination


def list_installed_models(models_root: Path) -> list[dict[str, Any]]:
    """Registered models, newest first, with their manifests."""
    models_root = Path(models_root).expanduser()
    if not models_root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for folder in sorted(models_root.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        manifest = folder / "model.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        data["path"] = str(folder)
        data["preview"] = str(folder / data.get("entrypoint", "idle.png"))
        items.append(data)
    items.sort(key=lambda item: int(item.get("added_at") or 0), reverse=True)
    return items


def delete_model(models_root: Path, slug: str) -> bool:
    models_root = Path(models_root).expanduser()
    target = (models_root / slug).resolve()
    root = models_root.resolve()
    if root not in target.parents:
        raise ModelImportError("Нельзя удалить папку вне каталога моделей.")
    if not target.is_dir():
        return False
    shutil.rmtree(target)
    return True


# ---------------------------------------------------------------- renderer


class PngTuberRenderer:
    """Frame renderer for PNGTuber packs: idle / talk / blink combinations."""

    def __init__(self) -> None:
        self._dir: Path | None = None
        self._frames: dict[str, QPixmap] = {}
        self._mode = CompanionMode.IDLE
        self._next_blink = time.monotonic() + 3.0
        self._blink_until = 0.0

    # -- CompanionRenderer contract ------------------------------------------
    def load_model(self, model_directory: str, entrypoint: str) -> None:
        directory = Path(model_directory)
        manifest = directory / "model.json"
        states: dict[str, str] = {}
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                states = dict(data.get("states") or {})
            except (OSError, ValueError):
                states = {}
        if not states:
            states = {state: name for name, state in FRAME_STATES.items() if (directory / name).is_file()}
        frames: dict[str, QPixmap] = {}
        for state, filename in states.items():
            path = directory / filename
            if not path.is_file():
                continue
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                frames[state] = pixmap
        if "idle" not in frames:
            raise ModelImportError("В модели нет рабочего кадра idle.png.")
        self._frames = frames
        self._dir = directory
        self._mode = CompanionMode.IDLE

    def apply_snapshot(self, snapshot: CompanionSnapshot) -> None:
        self._mode = snapshot.mode

    def render_status(self) -> dict[str, Any]:
        return {
            "renderer": "pngtuber",
            "frames": ",".join(sorted(self._frames)),
            "model": self._dir.name if self._dir else "",
        }

    def close(self) -> None:
        self._frames = {}
        self._dir = None

    # -- painting -------------------------------------------------------------
    @property
    def blink_active(self) -> bool:
        return time.monotonic() < self._blink_until

    def _maybe_blink(self) -> None:
        now = time.monotonic()
        if not self.blink_active and "blink" in self._frames and now >= self._next_blink:
            self._blink_until = now + 0.16
            self._next_blink = now + 2.0 + (int(now * 1000) % 4000) / 1000.0

    def paint(self, painter: QPainter, rect: QRectF, snapshot: CompanionSnapshot) -> None:
        if not self._frames:
            return
        self._maybe_blink()
        speaking = snapshot.mode == CompanionMode.SPEAKING
        if speaking:
            frame = self._frames.get("talk") or self._frames["idle"]
            if self.blink_active:
                frame = self._frames.get("blink_talk") or frame
        else:
            frame = self._frames["idle"]
            if self.blink_active:
                frame = self._frames.get("blink") or frame
        scaled = frame.scaled(
            rect.size().toSize(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = rect.x() + (rect.width() - scaled.width()) / 2
        y = rect.y() + (rect.height() - scaled.height())
        painter.drawPixmap(int(x), int(y), scaled)

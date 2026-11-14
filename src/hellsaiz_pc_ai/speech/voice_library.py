from __future__ import annotations

import json
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


VOICE_ID_PATTERN = re.compile(
    r"^(?P<language>[a-z]{2}_[A-Z]{2})-(?P<speaker>[a-z0-9_]+)-(?P<quality>low|medium|high)$"
)
VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
MAX_MODEL_BYTES = 1024 * 1024 * 1024


class VoiceLibraryError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstalledVoice:
    voice_id: str
    model_path: Path
    language: str
    license: str


def _voice_parts(voice_id: str) -> tuple[str, str, str, str]:
    match = VOICE_ID_PATTERN.fullmatch(voice_id.strip())
    if match is None:
        raise VoiceLibraryError(
            "Формат голоса: ru_RU-denis-medium (язык_регион-имя-качество)."
        )
    language = match.group("language")
    return language.split("_", 1)[0], language, match.group("speaker"), match.group("quality")


def _download(url: str, destination: Path, max_bytes: int) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Hellsaiz-PC-AI/0.1.4 voice-library"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > max_bytes:
                raise VoiceLibraryError("Файл модели превышает допустимый размер.")
            total = 0
            with destination.open("xb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise VoiceLibraryError("Загрузка превысила допустимый размер.")
                    output.write(chunk)
            if total == 0:
                raise VoiceLibraryError("Сервер вернул пустой файл.")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        destination.unlink(missing_ok=True)
        if isinstance(exc, VoiceLibraryError):
            raise
        raise VoiceLibraryError(f"Не удалось загрузить файл голоса: {exc}") from exc


def download_voice(voice_id: str, destination_dir: Path) -> InstalledVoice:
    """Download a Piper ONNX model, config and its MODEL_CARD atomically."""
    language_family, language, speaker, quality = _voice_parts(voice_id)
    voice_id = voice_id.strip()
    destination_dir.mkdir(parents=True, exist_ok=True)
    model = destination_dir / f"{voice_id}.onnx"
    config = destination_dir / f"{voice_id}.onnx.json"
    card = destination_dir / f"{voice_id}.MODEL_CARD"
    if model.is_file() and config.is_file() and card.is_file():
        return InstalledVoice(voice_id, model, language, _license_from_card(card))

    relative = f"{language_family}/{language}/{speaker}/{quality}"
    urls = {
        model: f"{VOICE_BASE_URL}/{relative}/{voice_id}.onnx",
        config: f"{VOICE_BASE_URL}/{relative}/{voice_id}.onnx.json",
        card: f"{VOICE_BASE_URL}/{relative}/MODEL_CARD",
    }
    with tempfile.TemporaryDirectory(prefix="hellsaiz-voice-", dir=destination_dir) as temp:
        staged: list[tuple[Path, Path]] = []
        try:
            for index, (target, url) in enumerate(urls.items()):
                temporary = Path(temp) / f"{index}.part"
                limit = MAX_MODEL_BYTES if target == model else 2 * 1024 * 1024
                _download(url, temporary, limit)
                staged.append((temporary, target))
            # Config must be valid JSON before activating the model.
            json.loads(staged[1][0].read_text(encoding="utf-8"))
            for temporary, target in staged:
                temporary.replace(target)
        except Exception:
            for target in urls:
                if not target.exists():
                    continue
            raise
    return InstalledVoice(voice_id, model, language, _license_from_card(card))


def _license_from_card(card: Path) -> str:
    try:
        text = card.read_text(encoding="utf-8")
    except OSError:
        return "Неизвестно — проверь MODEL_CARD"
    match = re.search(r"(?im)^\s*\*\s*License:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else "Не указана — проверь MODEL_CARD"


def list_installed_voices(directory: Path) -> list[InstalledVoice]:
    voices: list[InstalledVoice] = []
    if not directory.is_dir():
        return voices
    for model in sorted(directory.glob("*.onnx")):
        if model.is_symlink() or not model.is_file():
            continue
        config = Path(f"{model}.json")
        card = directory / f"{model.stem}.MODEL_CARD"
        if not config.is_file() or config.is_symlink():
            continue
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        espeak = data.get("espeak")
        language = str(espeak.get("voice") or "unknown") if isinstance(espeak, dict) else "unknown"
        voices.append(InstalledVoice(
            model.stem, model, language, _license_from_card(card)
        ))
    return voices


def remove_voice(voice_id: str, directory: Path) -> bool:
    _voice_parts(voice_id)
    model = directory / f"{voice_id}.onnx"
    removed = False
    for path in (
        model,
        Path(f"{model}.json"),
        directory / f"{voice_id}.MODEL_CARD",
    ):
        if path.is_symlink():
            raise VoiceLibraryError("Отказ: найден символический файл в библиотеке голосов.")
        if path.is_file():
            path.unlink()
            removed = True
    return removed

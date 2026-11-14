from __future__ import annotations

import shutil
import stat
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


VOSK_MODEL_ID = "vosk-model-small-ru-0.22"
VOSK_MODEL_URL = (
    "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
)
VOSK_MODEL_LICENSE = "Apache-2.0"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_FILES = 10_000


class ModelInstallError(RuntimeError):
    pass


def is_valid_vosk_model(model_dir: Path) -> bool:
    model_dir = Path(model_dir)
    if model_dir.is_symlink() or not model_dir.is_dir():
        return False
    required = (
        model_dir / "am" / "final.mdl",
        model_dir / "conf" / "model.conf",
        model_dir / "graph" / "words.txt",
    )
    return all(path.is_file() and not path.is_symlink() for path in required)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _download_archive(destination: Path) -> None:
    request = urllib.request.Request(
        VOSK_MODEL_URL,
        headers={"User-Agent": "Hellsaiz-PC-AI/0.1.4 Vosk-Model-Installer"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_ARCHIVE_BYTES:
                raise ModelInstallError("Архив Vosk превышает допустимый размер.")
            total = 0
            with destination.open("xb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise ModelInstallError("Загрузка Vosk превысила лимит размера.")
                    output.write(chunk)
            if total == 0:
                raise ModelInstallError("Сервер вернул пустой архив Vosk.")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        destination.unlink(missing_ok=True)
        if isinstance(exc, ModelInstallError):
            raise
        raise ModelInstallError(f"Не удалось загрузить модель Vosk: {exc}") from exc


def _safe_extract(archive_path: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    total_size = 0
    file_count = 0
    expected_root = VOSK_MODEL_ID
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > MAX_ARCHIVE_FILES:
                raise ModelInstallError("Архив Vosk содержит недопустимое количество файлов.")
            for info in entries:
                name = info.filename
                if not name or "\\" in name:
                    raise ModelInstallError("Архив Vosk содержит небезопасный путь.")
                relative = PurePosixPath(name)
                if (
                    relative.is_absolute()
                    or any(part in {"", ".", ".."} or ":" in part for part in relative.parts)
                ):
                    raise ModelInstallError("Архив Vosk содержит путь за пределами модели.")
                if not relative.parts or relative.parts[0] != expected_root:
                    raise ModelInstallError("Архив Vosk имеет неожиданный корневой каталог.")
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise ModelInstallError("Символические ссылки в архиве Vosk запрещены.")
                file_type = stat.S_IFMT(mode)
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ModelInstallError("Архив Vosk содержит специальный файл.")
                if info.is_dir():
                    continue
                file_count += 1
                total_size += info.file_size
                if file_count > MAX_ARCHIVE_FILES or total_size > MAX_EXTRACTED_BYTES:
                    raise ModelInstallError("Распакованный объём модели Vosk превышает лимит.")
                if info.file_size and info.compress_size == 0:
                    raise ModelInstallError("Архив Vosk содержит некорректную запись.")
                if info.compress_size and info.file_size / info.compress_size > 500:
                    raise ModelInstallError("Архив Vosk содержит подозрительно сжатый файл.")

                target = destination.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(info, "r") as source, target.open("xb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > info.file_size:
                            raise ModelInstallError("Размер файла в архиве не совпадает с заголовком.")
                        output.write(chunk)
                if written != info.file_size:
                    raise ModelInstallError("Архив Vosk содержит неполный файл.")
    except zipfile.BadZipFile as exc:
        raise ModelInstallError("Скачанный файл не является корректным ZIP-архивом.") from exc

    model_path = destination / expected_root
    if not is_valid_vosk_model(model_path):
        raise ModelInstallError(
            "Архив распакован, но обязательные файлы модели Vosk не найдены."
        )
    return model_path


def install_vosk_small_ru(destination_dir: Path) -> Path:
    """Install the official 45 MB small Russian Vosk model atomically."""
    destination_dir = Path(destination_dir).expanduser()
    if destination_dir.is_symlink():
        raise ModelInstallError("Каталог моделей Vosk не должен быть символической ссылкой.")
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / VOSK_MODEL_ID
    if is_valid_vosk_model(target):
        return target
    if target.is_symlink():
        raise ModelInstallError("Целевая папка модели Vosk является символической ссылкой.")

    backup = destination_dir / f".{VOSK_MODEL_ID}.previous"
    if backup.is_symlink():
        raise ModelInstallError("Резервная папка модели Vosk является символической ссылкой.")
    _remove_path(backup)

    with tempfile.TemporaryDirectory(
        prefix="hellsaiz-vosk-", dir=destination_dir
    ) as temporary:
        temporary_dir = Path(temporary)
        archive_path = temporary_dir / "model.zip"
        _download_archive(archive_path)
        extracted_root = _safe_extract(archive_path, temporary_dir / "extract")
        staged_model = temporary_dir / "staged-model"
        extracted_root.replace(staged_model)

        had_previous = target.exists()
        if had_previous:
            target.replace(backup)
        try:
            staged_model.replace(target)
            if not is_valid_vosk_model(target):
                raise ModelInstallError(
                    "Установленная модель Vosk не прошла проверку целостности."
                )
        except Exception:
            if target.exists():
                _remove_path(target)
            if had_previous and backup.exists():
                backup.replace(target)
            raise

    _remove_path(backup)
    return target

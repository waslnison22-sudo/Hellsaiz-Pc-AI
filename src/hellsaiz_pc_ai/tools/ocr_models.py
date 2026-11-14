from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAX_MODEL_BYTES = 120 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 90
CHUNK_BYTES = 1024 * 1024

RUSSIAN_OCR_MODELS = {
    "det": {
        "filename": "ch_PP-OCRv5_det_mobile.onnx",
        "url": "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx",
        "sha256": "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
    },
    "cls": {
        "filename": "ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
        "url": "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/cls/ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
        "sha256": "54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7",
    },
    "rec": {
        "filename": "cyrillic_PP-OCRv5_rec_mobile.onnx",
        "url": "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/cyrillic_PP-OCRv5_rec_mobile.onnx",
        "sha256": "90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711",
    },
}


class OcrModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrModelsStatus:
    ready: bool
    missing: tuple[str, ...]
    invalid: tuple[str, ...]


def model_path(root: Path, key: str) -> Path:
    if key not in RUSSIAN_OCR_MODELS:
        raise ValueError(f"Unknown OCR model key: {key}")
    return Path(root) / RUSSIAN_OCR_MODELS[key]["filename"]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_russian_ocr_models(root: Path) -> OcrModelsStatus:
    missing: list[str] = []
    invalid: list[str] = []
    for key, metadata in RUSSIAN_OCR_MODELS.items():
        path = model_path(root, key)
        if not path.is_file():
            missing.append(key)
            continue
        try:
            if path.stat().st_size <= 0 or path.stat().st_size > MAX_MODEL_BYTES:
                invalid.append(key)
            elif _hash_file(path) != metadata["sha256"]:
                invalid.append(key)
        except OSError:
            invalid.append(key)
    return OcrModelsStatus(not missing and not invalid, tuple(missing), tuple(invalid))


def download_russian_ocr_models(
    root: Path,
    *,
    opener: Any = urlopen,
    timeout_seconds: int = DOWNLOAD_TIMEOUT_SECONDS,
    progress: Any | None = None,
) -> OcrModelsStatus:
    """Explicitly download and SHA-256 verify the Russian OCR models."""
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 5 <= timeout_seconds <= 300:
        raise ValueError("Тайм-аут загрузки моделей OCR должен быть от 5 до 300 секунд.")
    target_root = Path(root).expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    for key, metadata in RUSSIAN_OCR_MODELS.items():
        target = model_path(target_root, key)
        if target.is_file():
            try:
                if target.stat().st_size <= MAX_MODEL_BYTES and _hash_file(target) == metadata["sha256"]:
                    if progress:
                        progress(key, "already-installed")
                    continue
            except OSError:
                pass

        temporary = target.with_suffix(target.suffix + ".download")
        temporary.unlink(missing_ok=True)
        request = Request(
            metadata["url"],
            headers={
                "User-Agent": "HellsaizPC_AI-OCR-ModelInstaller/0.1",
                "Accept": "application/octet-stream",
            },
        )
        digest = hashlib.sha256()
        downloaded = 0
        try:
            try:
                response = opener(request, timeout=timeout_seconds)
            except TypeError:
                response = opener(request)
            with response:
                declared_size = response.headers.get("Content-Length")
                if declared_size:
                    try:
                        if int(declared_size) > MAX_MODEL_BYTES:
                            raise OcrModelError(f"Модель {key} превышает допустимый размер.")
                    except ValueError as exc:
                        raise OcrModelError("Сервер вернул некорректный Content-Length.") from exc
                with temporary.open("wb") as output:
                    while True:
                        chunk = response.read(CHUNK_BYTES)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > MAX_MODEL_BYTES:
                            raise OcrModelError(f"Модель {key} превышает допустимый размер.")
                        digest.update(chunk)
                        output.write(chunk)
            if downloaded <= 0:
                raise OcrModelError(f"Сервер вернул пустую модель {key}.")
            if digest.hexdigest() != metadata["sha256"]:
                raise OcrModelError(f"SHA-256 модели {key} не совпал с официальным манифестом.")
            os.replace(temporary, target)
            if progress:
                progress(key, "downloaded")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            temporary.unlink(missing_ok=True)
            raise OcrModelError(f"Не удалось загрузить модель {key} ({type(exc).__name__}).") from exc
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    status = check_russian_ocr_models(target_root)
    if not status.ready:
        raise OcrModelError(
            f"Проверка локальных OCR-моделей не прошла. Отсутствуют: {status.missing}; повреждены: {status.invalid}."
        )
    return status

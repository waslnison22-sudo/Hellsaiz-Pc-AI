from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


MAX_IMAGE_EDGE = 2560
MAX_TEXT_LINES = 100
MAX_TEXT_CHARS = 12000
MIN_CONFIDENCE = 0.25

_engine: Any | None = None
_engine_lock = threading.Lock()


def _capture_primary_monitor() -> Any:
    try:
        import numpy as np
        from mss import MSS
    except ImportError as exc:
        raise RuntimeError(
            'Для локального OCR нужны vision-зависимости. Установи пакет с extra: pip install -e ".[vision]".'
        ) from exc

    with MSS() as capture:
        monitor = capture.primary_monitor
        if monitor.width <= 0 or monitor.height <= 0:
            raise RuntimeError("Windows не вернула размеры основного монитора.")
        screenshot = capture.grab(monitor)
        image = np.asarray(screenshot)[:, :, :3]
    height, width = image.shape[:2]
    scale = max(height / MAX_IMAGE_EDGE, width / MAX_IMAGE_EDGE, 1.0)
    if scale > 1.0:
        step = int(scale + 0.5)
        image = image[::step, ::step, :]
    return image


def _get_engine() -> Any:
    global _engine
    with _engine_lock:
        if _engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise RuntimeError(
                    'Локальный OCR не установлен. Установи пакет с extra: pip install -e ".[vision]".'
                ) from exc
            _engine = RapidOCR()
        return _engine


def _extract_text(result: Any) -> list[str]:
    if result is None:
        return []
    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if texts is None:
        raise RuntimeError("OCR-движок вернул неподдерживаемую структуру результата.")
    lines: list[str] = []
    total = 0
    for index, raw_text in enumerate(texts):
        if not isinstance(raw_text, str):
            continue
        text = " ".join(raw_text.split()).strip()
        if not text:
            continue
        if scores is not None and index < len(scores):
            try:
                if float(scores[index]) < MIN_CONFIDENCE:
                    continue
            except (TypeError, ValueError):
                continue
        remaining = MAX_TEXT_CHARS - total
        if remaining <= 0:
            break
        text = text[:remaining]
        lines.append(text)
        total += len(text) + 1
        if len(lines) >= MAX_TEXT_LINES:
            break
    return lines


def read_primary_screen_text(
    *,
    capture: Callable[[], Any] = _capture_primary_monitor,
    engine_factory: Callable[[], Any] = _get_engine,
) -> ToolResult:
    try:
        image = capture()
        engine = engine_factory()
        output = engine(image)
        lines = _extract_text(output)
        if not lines:
            return ToolResult(True, "Текст на основном экране не обнаружен.", {"line_count": 0})
        rendered = "\n".join(lines)
        if len(lines) >= MAX_TEXT_LINES:
            rendered += "\n… [достигнут лимит OCR]"
        return ToolResult(
            True,
            "Результат локального OCR основного монитора:\n" + rendered,
            {"line_count": len(lines), "saved_to_disk": False, "sent_to_network": False},
        )
    except Exception as exc:
        return ToolResult(False, f"Локальный OCR не выполнен ({type(exc).__name__}): {exc}")


def register_screen_ocr_tools(
    registry: ToolRegistry,
    *,
    enabled: Callable[[], bool],
) -> None:
    def run(_arguments: dict[str, Any]) -> ToolResult:
        try:
            is_enabled = bool(enabled())
        except Exception as exc:
            return ToolResult(False, f"Не удалось прочитать разрешение OCR ({type(exc).__name__}).")
        if not is_enabled:
            return ToolResult(
                False,
                "Распознавание экрана выключено. Включи локальный OCR в настройках приложения.",
            )
        return read_primary_screen_text()

    registry.register(ToolSpec(
        name="read_screen_text",
        description=(
            "Сделать снимок основного монитора в памяти и распознать видимый текст локальным OCR. "
            "Снимок не сохраняется и не отправляется в сеть."
        ),
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk=RiskLevel.CONFIRM,
        handler=run,
    ))

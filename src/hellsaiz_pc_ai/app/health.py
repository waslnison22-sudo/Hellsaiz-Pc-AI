from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


HealthLevel = Literal["ok", "warning", "error"]
MAX_WORKFLOW_DIAGNOSTIC_BYTES = 1_000_000


@dataclass(frozen=True)
class HealthItem:
    component: str
    level: HealthLevel
    message: str


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def collect_speech_health(
    *,
    stt_primary: str,
    stt_fallback: str,
    vosk_model_path: Path,
    whisper_executable: Path | None,
    whisper_model: Path | None,
    tts_engine: str,
    piper_model_path: Path | None,
    microphone_device: str = "",
    wake_enabled: bool = False,
    is_windows: bool | None = None,
) -> list[HealthItem]:
    """Return concise diagnostics without opening the microphone or playing audio."""
    windows = os.name == "nt" if is_windows is None else is_windows
    checks: list[HealthItem] = []
    mic_ok = _module_available("sounddevice")
    if not mic_ok:
        checks.append(HealthItem(
            "Микрофон", "warning",
            'Не установлен sounddevice. Выполни: pip install -e ".[voice]"',
        ))
    else:
        try:
            from hellsaiz_pc_ai.speech.capture import list_input_devices

            devices = list_input_devices()
            device_names = {item.name for item in devices}
            device_labels = {item.display_name for item in devices}
            if not devices:
                checks.append(HealthItem(
                    "Микрофон", "warning", "Windows не обнаружила входных микрофонов.",
                ))
            elif microphone_device and microphone_device not in device_names | device_labels:
                checks.append(HealthItem(
                    "Микрофон", "warning",
                    f"Выбранное устройство «{microphone_device}» не найдено.",
                ))
            else:
                current_name = microphone_device or "системное устройство по умолчанию"
                checks.append(HealthItem(
                    "Микрофон", "ok",
                    f"Входное устройство доступно: {current_name}.",
                ))
        except Exception as exc:
            checks.append(HealthItem(
                "Микрофон", "warning", f"Не удалось проверить входные устройства: {exc}",
            ))

    def check_stt(name: str, *, required: bool) -> None:
        severity: HealthLevel = "error" if required else "warning"
        if name == "vosk":
            if not _module_available("vosk"):
                checks.append(HealthItem(
                    f"STT / {name}", severity,
                    'Пакет Vosk не установлен. Выполни: pip install -e ".[voice]"',
                ))
            elif not Path(vosk_model_path).is_dir():
                # Not installed is fixable in the UI, so it is a warning, not
                # an error: the Diagnostics tab offers a download button.
                checks.append(HealthItem(
                    f"STT / {name}", "warning",
                    f"Модель не загружена: {vosk_model_path}. Скачай её кнопкой "
                    "«Скачать модель» в Диагностике.",
                ))
            else:
                checks.append(HealthItem("STT / Vosk", "ok", "Пакет и локальная модель найдены."))
            return
        if name == "whisper.cpp":
            if whisper_executable is None or not Path(whisper_executable).is_file():
                checks.append(HealthItem(
                    "STT / Whisper.cpp", severity, "Не найден whisper-cli.exe.",
                ))
            elif whisper_model is None or not Path(whisper_model).is_file():
                checks.append(HealthItem(
                    "STT / Whisper.cpp", severity, "Не найдена GGML-модель Whisper.cpp.",
                ))
            else:
                checks.append(HealthItem(
                    "STT / Whisper.cpp", "ok", "CLI и локальная GGML-модель найдены.",
                ))

    check_stt(stt_primary, required=True)
    if stt_fallback and stt_fallback != "none" and stt_fallback != stt_primary:
        check_stt(stt_fallback, required=False)
    if wake_enabled and stt_primary != "vosk" and stt_fallback != "vosk":
        check_stt("vosk", required=False)

    if tts_engine == "piper":
        if not _module_available("piper"):
            checks.append(HealthItem(
                "TTS / Piper", "error",
                'Пакет piper-tts не установлен. Выполни: pip install -e ".[voice]"',
            ))
        elif piper_model_path is None or not Path(piper_model_path).is_file():
            checks.append(HealthItem(
                "TTS / Piper", "warning",
                "Модель не загружена — её можно скачать в «Настройках».",
            ))
        else:
            checks.append(HealthItem(
                "TTS / Piper", "ok", "Пакет и локальная ONNX-модель найдены.",
            ))
    elif tts_engine == "sapi5":
        if not windows:
            checks.append(HealthItem(
                "TTS / SAPI5", "warning", "SAPI5 работает только в Windows.",
            ))
        elif not _module_available("pyttsx3"):
            checks.append(HealthItem(
                "TTS / SAPI5", "warning",
                'Не установлен мост pyttsx3. Выполни: pip install -e ".[voice]"',
            ))
        else:
            checks.append(HealthItem(
                "TTS / SAPI5", "ok", "Windows SAPI5 доступен; установленный голос проверяется при воспроизведении.",
            ))
    else:
        checks.append(HealthItem(
            "TTS", "warning", f"Неизвестный выбранный движок: {tts_engine}",
        ))
    return checks

def collect_storage_health(
    *, database_path: Path, workflows_path: Path, low_disk_warning_bytes: int = 128 * 1024 * 1024
) -> list[HealthItem]:
    """Inspect local storage without creating, migrating, or modifying user data."""
    database_path = Path(database_path)
    workflows_path = Path(workflows_path)
    checks: list[HealthItem] = []

    if not database_path.is_file():
        checks.append(HealthItem(
            "История SQLite", "error",
            f"Файл базы истории не найден: {database_path}",
        ))
    else:
        connection: sqlite3.Connection | None = None
        try:
            database_uri = database_path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(database_uri, uri=True, timeout=1.5)
            connection.execute("PRAGMA query_only = ON")
            integrity = connection.execute("PRAGMA quick_check(1)").fetchone()
            if not integrity or integrity[0] != "ok":
                detail = str(integrity[0])[:240] if integrity else "нет результата"
                checks.append(HealthItem(
                    "История SQLite", "error",
                    f"Проверка целостности не пройдена: {detail}",
                ))
            else:
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                missing = {"messages", "reminders"} - tables
                if missing:
                    checks.append(HealthItem(
                        "История SQLite", "error",
                        "Не найдены таблицы: " + ", ".join(sorted(missing)),
                    ))
                else:
                    checks.append(HealthItem(
                        "История SQLite", "ok",
                        "База открывается только для чтения; quick_check и схема пройдены.",
                    ))
        except (sqlite3.Error, OSError, ValueError) as exc:
            checks.append(HealthItem(
                "История SQLite", "error",
                f"Не удалось безопасно проверить базу: {type(exc).__name__}: {exc}",
            ))
        finally:
            if connection is not None:
                connection.close()

    if not workflows_path.exists():
        checks.append(HealthItem(
            "Библиотека сценариев", "warning",
            "Папка сценариев ещё не создана; она появится при инициализации библиотеки.",
        ))
    elif not workflows_path.is_dir():
        checks.append(HealthItem(
            "Библиотека сценариев", "error",
            f"Путь сценариев не является папкой: {workflows_path}",
        ))
    else:
        from hellsaiz_pc_ai.workflows.graph import WorkflowGraph

        valid_count = 0
        invalid_names: list[str] = []
        try:
            for path in sorted(workflows_path.glob("*.json")):
                try:
                    if path.stat().st_size > MAX_WORKFLOW_DIAGNOSTIC_BYTES:
                        raise ValueError(
                            f"workflow file exceeds {MAX_WORKFLOW_DIAGNOSTIC_BYTES} bytes"
                        )
                    graph_data = json.loads(path.read_text(encoding="utf-8"))
                    WorkflowGraph.from_dict(graph_data)
                    valid_count += 1
                except (OSError, TypeError, ValueError, json.JSONDecodeError, RecursionError):
                    invalid_names.append(path.name)
        except OSError as exc:
            checks.append(HealthItem(
                "Библиотека сценариев", "error",
                f"Не удалось прочитать папку сценариев: {exc}",
            ))
        else:
            if invalid_names:
                examples = ", ".join(invalid_names[:4])
                suffix = " …" if len(invalid_names) > 4 else ""
                checks.append(HealthItem(
                    "Библиотека сценариев", "warning",
                    f"Рабочих сценариев: {valid_count}; повреждённых файлов: "
                    f"{len(invalid_names)} ({examples}{suffix}).",
                ))
            else:
                checks.append(HealthItem(
                    "Библиотека сценариев", "ok",
                    f"Папка доступна; корректных сценариев: {valid_count}.",
                ))

    data_root = database_path.parent
    if not data_root.is_dir():
        checks.append(HealthItem(
            "Пользовательское хранилище", "error",
            f"Каталог данных недоступен: {data_root}",
        ))
    elif not os.access(data_root, os.W_OK):
        checks.append(HealthItem(
            "Пользовательское хранилище", "error",
            f"Нет прав на запись в каталог данных: {data_root}",
        ))
    else:
        try:
            free_bytes = shutil.disk_usage(data_root).free
            free_mib = free_bytes / (1024 * 1024)
            if free_bytes < low_disk_warning_bytes:
                checks.append(HealthItem(
                    "Свободное место", "warning",
                    f"Осталось {free_mib:.0f} МиБ; загрузка моделей и обновлений может не поместиться.",
                ))
            else:
                checks.append(HealthItem(
                    "Пользовательское хранилище", "ok",
                    f"Каталог доступен для записи; свободно {free_mib:.0f} МиБ.",
                ))
        except OSError as exc:
            checks.append(HealthItem(
                "Пользовательское хранилище", "warning",
                f"Не удалось определить свободное место: {exc}",
            ))
    return checks


def summarize_health(checks: list[HealthItem]) -> tuple[HealthLevel, str]:
    """Return the worst observed level and compact counts for the settings UI."""
    counts = {
        level: sum(item.level == level for item in checks)
        for level in ("ok", "warning", "error")
    }
    if counts["error"]:
        level: HealthLevel = "error"
    elif counts["warning"] or not checks:
        level = "warning"
    else:
        level = "ok"
    summary = (
        f"OK: {counts['ok']} · предупреждения: {counts['warning']} · "
        f"ошибки: {counts['error']}"
    )
    if not checks:
        summary = "Диагностика не вернула результатов."
    return level, summary

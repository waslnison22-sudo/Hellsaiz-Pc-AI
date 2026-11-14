from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


HealthLevel = Literal["ok", "warning", "error"]


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
                checks.append(HealthItem(
                    f"STT / {name}", severity,
                    f"Папка модели не найдена: {vosk_model_path}",
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
                "TTS / Piper", "error", "Выбранная ONNX-модель Piper не найдена.",
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

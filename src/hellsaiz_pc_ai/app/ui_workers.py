"""Background workers and signal bridges for the desktop UI.

Extracted from the former single ``main()`` in ``app/desktop.py`` so the UI
code can import them explicitly instead of redefining nested classes inside
one closure scope. Every class either takes plain parameters or explicit UI
callbacks/widgets; no class silently captures surrounding function state.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from hellsaiz_pc_ai import startup_task
from hellsaiz_pc_ai.network import v2raytun
from hellsaiz_pc_ai.secure_store import SecureStoreError, load_secret
from hellsaiz_pc_ai.speech.piper import PiperSynthesizer
from hellsaiz_pc_ai.speech.voice_library import (
    VoiceLibraryError,
    download_voice,
    list_installed_voices,
)
from hellsaiz_pc_ai.tools.ocr_models import (
    check_russian_ocr_models,
    download_russian_ocr_models,
)
from hellsaiz_pc_ai.update_client import (
    UpdateCheckError,
    check_latest_release,
    download_update,
)


class HotkeyBridge(QObject):
    """Re-emits a global hotkey event from the OS listener to the GUI thread."""

    activated = Signal(str, str)


class HotkeyDispatcher(QObject):
    """Routes a hotkey signal into a plain callback on the GUI thread."""

    def __init__(self, callback: Any) -> None:
        super().__init__()
        self.callback = callback

    @Slot(str, str)
    def dispatch(self, workflow_id: str, combo: str) -> None:
        self.callback(workflow_id, combo)


class VoskModelDownloadWorker(QThread):
    """Downloads and unpacks the local Vosk RU model in the background."""

    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, destination_dir: Path) -> None:
        super().__init__()
        self.destination_dir = destination_dir

    def run(self) -> None:
        try:
            from hellsaiz_pc_ai.speech.model_library import install_vosk_small_ru

            model_path = install_vosk_small_ru(self.destination_dir)
            self.completed.emit(str(model_path))
        except Exception as exc:
            self.failed.emit(str(exc))


class WakeListenerWorker(QThread):
    """Runs the always-listening wake-word detector in a dedicated thread."""

    command = Signal(str)
    status = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        model_dir: Path,
        aliases: tuple[str, ...],
        device: str | None = None,
    ) -> None:
        super().__init__()
        self.model_dir = model_dir
        self.aliases = aliases
        self.device = device
        self.listener = None

    def run(self) -> None:
        try:
            from hellsaiz_pc_ai.speech.wake_listener import WakeWordListener

            self.listener = WakeWordListener(
                self.model_dir,
                self.aliases,
                on_command=self.command.emit,
                on_status=self.status.emit,
                device=self.device,
            )
            self.listener.listen()
        except Exception as exc:
            self.failed.emit(str(exc))

    def stop_listener(self) -> None:
        if self.listener is not None:
            self.listener.stop()


class WakeListenerDispatcher(QObject):
    """Delivers wake-listener signals to explicit GUI-thread callbacks."""

    def __init__(
        self,
        on_command: Any,
        on_status: Any,
        on_failed: Any,
    ) -> None:
        super().__init__()
        self.on_command = on_command
        self.on_status = on_status
        self.on_failed = on_failed

    @Slot(str)
    def dispatch_command(self, prompt: str) -> None:
        self.on_command(prompt)

    @Slot(str)
    def dispatch_status(self, message: str) -> None:
        self.on_status(message)

    @Slot(str)
    def dispatch_failed(self, message: str) -> None:
        self.on_failed(message)


class ProviderHealthWorker(QThread):
    """Runs a provider health check off the GUI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, provider: Any) -> None:
        super().__init__()
        self.provider = provider

    def run(self) -> None:
        try:
            self.completed.emit(self.provider.health_check())
        except Exception as exc:
            self.failed.emit(str(exc))


class VoiceDownloadWorker(QThread):
    """Downloads a Piper voice into the user voice library."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, voice_id: str, target_dir: Path) -> None:
        super().__init__()
        self.voice_id = voice_id
        self.target_dir = target_dir

    def run(self) -> None:
        try:
            result = download_voice(self.voice_id, self.target_dir)
            self.completed.emit(result)
        except (VoiceLibraryError, OSError, ValueError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            logging.exception("Piper voice download failed")
            self.failed.emit(f"Ошибка загрузки голоса: {exc}")


class VoiceTestWorker(QThread):
    """Plays a short test phrase with the selected speech engine."""

    completed = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        engine: str,
        voice_name: str,
        model_path: Path | None,
        rate: int,
        volume: float,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.voice_name = voice_name
        self.model_path = model_path
        self.rate = rate
        self.volume = volume

    def run(self) -> None:
        try:
            sample = "Привет. Я Хеллсайз. Проверка голосового движка завершена."
            if self.engine == "piper":
                if self.model_path is None:
                    raise FileNotFoundError("Не выбрана локальная модель Piper.")
                PiperSynthesizer(self.model_path).speak(sample)
            elif self.engine == "sapi5":
                from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer

                Sapi5Synthesizer(
                    self.voice_name, self.rate, self.volume
                ).speak(sample)
            else:
                raise ValueError(f"Неизвестный голосовой движок: {self.engine}")
            self.completed.emit(f"Проверка {self.engine} завершена.")
        except Exception as exc:
            self.failed.emit(str(exc))


class SapiVoiceListWorker(QThread):
    """Enumerates installed Windows SAPI5 voices off the GUI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, rate: int, volume: float) -> None:
        super().__init__()
        self.rate = rate
        self.volume = volume

    def run(self) -> None:
        try:
            from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer

            voices = Sapi5Synthesizer("", self.rate, self.volume).list_voices()
            self.completed.emit(voices)
        except Exception as exc:
            self.failed.emit(str(exc))


class SystemHealthWorker(QThread):
    """Collects speech/storage diagnostics without touching GUI widgets."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        stt_profile: dict[str, Any],
        microphone_device: str,
        wake_enabled: bool,
        voice_id: str,
        tts_engine: str,
        *,
        voices_dir: Path,
        database_path: Path,
        workflows_path: Path,
    ) -> None:
        super().__init__()
        self.stt_profile = dict(stt_profile)
        self.microphone_device = microphone_device
        self.wake_enabled = wake_enabled
        self.voice_id = voice_id
        self.tts_engine = tts_engine
        self.voices_dir = voices_dir
        self.database_path = database_path
        self.workflows_path = workflows_path

    def run(self) -> None:
        try:
            from hellsaiz_pc_ai.app.health import collect_speech_health, collect_storage_health

            voice_models = list_installed_voices(self.voices_dir)
            selected_model = next(
                (voice for voice in voice_models if voice.voice_id == self.voice_id), None
            )
            checks = collect_speech_health(
                stt_primary=self.stt_profile["primary"],
                stt_fallback=self.stt_profile["fallback"],
                vosk_model_path=Path(self.stt_profile["vosk_model_path"]),
                whisper_executable=(
                    Path(self.stt_profile["whisper_cpp_executable"])
                    if self.stt_profile["whisper_cpp_executable"] else None
                ),
                whisper_model=(
                    Path(self.stt_profile["whisper_cpp_model"])
                    if self.stt_profile["whisper_cpp_model"] else None
                ),
                tts_engine=self.tts_engine,
                piper_model_path=selected_model.model_path if selected_model else None,
                microphone_device=self.microphone_device,
                wake_enabled=self.wake_enabled,
            )
            checks.extend(collect_storage_health(
                database_path=self.database_path,
                workflows_path=self.workflows_path,
            ))
            self.completed.emit(checks)
        except Exception as exc:
            logging.exception("System diagnostics failed")
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class SystemHealthBridge(QObject):
    """Delivers diagnostics results to explicit status widgets."""

    def __init__(
        self,
        *,
        summary_status: Any,
        detail_status: Any,
        health_button: Any,
        workers_list: list[QThread],
        on_completed: Any,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._summary_status = summary_status
        self._detail_status = detail_status
        self._health_button = health_button
        self._workers_list = workers_list
        self._on_completed = on_completed

    @Slot(object)
    def completed(self, checks: list[Any]) -> None:
        self._on_completed(checks)

    @Slot(str)
    def failed(self, message: str) -> None:
        self._summary_status.setText("ДИАГНОСТИКА НЕ ЗАВЕРШЕНА")
        self._detail_status.setText(f"Не удалось выполнить диагностику: {message}")

    @Slot()
    def finished(self) -> None:
        self._health_button.setEnabled(True)
        for worker in tuple(self._workers_list):
            if not worker.isRunning():
                self._workers_list.remove(worker)


class OcrModelsWorker(QThread):
    """Checks or downloads the local Russian OCR models."""

    progress = Signal(str, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, *, download: bool, models_root: Path) -> None:
        super().__init__()
        self.download = download
        self.models_root = models_root

    def run(self) -> None:
        try:
            if self.download:
                status = download_russian_ocr_models(
                    self.models_root,
                    progress=self.progress.emit,
                )
            else:
                status = check_russian_ocr_models(self.models_root)
            self.completed.emit(status)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class NetworkProbeWorker(QThread):
    """Builds the v2RayTun network status without blocking the GUI."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self.config = dict(config)

    def run(self) -> None:
        try:
            result = v2raytun.build_network_status(
                self.config["executable_path"],
                self.config["proxy_url"],
                self.config["health_url"],
                require_proxy=self.config["require_proxy_for_telegram"],
            )
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class TelegramStatusBridge(QObject):
    """Relays Telegram worker status text into the GUI thread."""

    status = Signal(str)


class StartupTaskWorker(QThread):
    """Registers or removes the Windows Task Scheduler autostart entry."""

    completed = Signal(bool, str)

    def __init__(self, enabled: bool, target: Path) -> None:
        super().__init__()
        self.enabled = enabled
        self.target = target

    def run(self) -> None:
        try:
            if self.enabled:
                startup_task.register_startup_task(self.target)
            else:
                startup_task.unregister_startup_task()
            registered = startup_task.is_registered()
            if registered != self.enabled:
                raise startup_task.StartupTaskError(
                    "Планировщик не подтвердил запрошенное состояние автозапуска."
                )
            self.completed.emit(
                registered,
                "Автозапуск включён при входе в Windows."
                if registered else "Автозапуск отключён."
            )
        except startup_task.StartupTaskError as exc:
            self.completed.emit(not self.enabled, str(exc))


class UpdateWorker(QThread):
    """Checks the release channel and optionally downloads the update."""

    checked = Signal(object)
    downloaded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        data_dir: Path,
        current_version: str,
        install_root: Path | None,
        *,
        download: bool = False,
    ) -> None:
        super().__init__()
        self.download = download
        self.data_dir = data_dir
        self.current_version = current_version
        self.install_root = install_root

    def run(self) -> None:
        try:
            key_path = self.data_dir / "update_key.dpapi"
            access_key = load_secret(key_path)
            if not access_key.strip():
                raise UpdateCheckError(
                    "Не сохранён GitHub Token. Создай Fine-grained token для "
                    "waslnison22-sudo/Hellsaiz-Pc-AI с правом Contents: Read "
                    "и сохрани его в этом разделе."
                )
            result = check_latest_release(self.current_version, access_key)
            self.checked.emit(result)
            if self.download and result.update_available:
                if self.install_root is None:
                    raise UpdateCheckError("Установочная папка не определена.")
                prepared = download_update(result, access_key, self.install_root)
                self.downloaded.emit(prepared)
        except (UpdateCheckError, SecureStoreError, OSError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            logging.exception("Update operation failed")
            self.failed.emit(f"Ошибка обновления: {exc}")

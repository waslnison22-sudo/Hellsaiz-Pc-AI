from __future__ import annotations

import atexit
import json
import logging
import tempfile
from html import escape
from pathlib import Path
from typing import Any

from hellsaiz_pc_ai.app_catalog import (
    AppCandidate,
    add_candidate,
    catalog_mappings,
    discover_windows_apps,
    load_user_catalog,
)
from hellsaiz_pc_ai.config import Settings, load_settings
from hellsaiz_pc_ai.core.commands import CommandRouter
from hellsaiz_pc_ai.secure_store import SecureStoreError, load_secret, save_secret
from hellsaiz_pc_ai.update_client import (
    PreparedUpdate,
    UpdateCheckError,
    UpdateInfo,
    check_latest_release,
    download_update,
)
from hellsaiz_pc_ai.install_layout import installed_app_root, installed_version
from hellsaiz_pc_ai.version import APP_VERSION
from hellsaiz_pc_ai.core.orchestrator import AssistantOrchestrator
from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.hotkeys import GlobalHotkeyService, HotkeyUnavailableError
from hellsaiz_pc_ai.providers.openai_compatible import OpenAICompatibleProvider, ProviderError
from hellsaiz_pc_ai.storage.reminders import ReminderStore
from hellsaiz_pc_ai.storage.sqlite_store import ChatStore
from hellsaiz_pc_ai.tools.clipboard import register_clipboard_tools
from hellsaiz_pc_ai.tools.reminders import register_reminder_tools
from hellsaiz_pc_ai.tools.system import register_system_tools
from hellsaiz_pc_ai.tools.public_info import register_public_info_tools
from hellsaiz_pc_ai.app.wallpaper import WallpaperError, WallpaperStore
from hellsaiz_pc_ai.app.shortcuts import ensure_desktop_shortcut
from hellsaiz_pc_ai.app.single_instance import SingleInstanceLock
from hellsaiz_pc_ai.speech.voice_library import (
    VoiceLibraryError, download_voice, list_installed_voices,
)
from hellsaiz_pc_ai.speech.piper import PiperSynthesizer
from hellsaiz_pc_ai.tools.windows import register_windows_tools
from hellsaiz_pc_ai.tools.window_control import register_window_tools
from hellsaiz_pc_ai.workflows.builder import append_hour_condition, append_repeat_action, append_tool_action, append_wait_action, append_weekday_condition, terminal_nodes
from hellsaiz_pc_ai.workflows.graph import WorkflowGraph, WorkflowGraphRunner, WorkflowTrigger
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary
from hellsaiz_pc_ai.workflows.scheduler import WorkflowScheduler


def build_runtime(settings: Settings):
    registry = ToolRegistry()
    register_system_tools(registry)
    register_public_info_tools(registry)

    catalog_path = settings.workflows_path.parent / "apps.json"
    try:
        custom_apps = load_user_catalog(catalog_path)
    except ValueError as exc:
        logging.warning("Saved app catalog is invalid: %s", exc)
        custom_apps = []
    discovered_allowed, discovered_aliases = catalog_mappings(custom_apps)
    allowed_apps = dict(settings.allowed_apps)
    allowed_apps.update(discovered_allowed)
    app_aliases = dict(settings.app_aliases)
    claimed_aliases = {
        CommandRouter._normalize_phrase(alias): key
        for key in allowed_apps
        for alias in (key, *app_aliases.get(key, ()))
    }
    for key, aliases in discovered_aliases.items():
        safe_aliases = []
        for alias in aliases:
            normalized = CommandRouter._normalize_phrase(alias)
            owner = claimed_aliases.get(normalized)
            if owner is None or owner == key:
                claimed_aliases[normalized] = key
                safe_aliases.append(alias)
        app_aliases[key] = tuple(safe_aliases)

    register_windows_tools(registry, allowed_apps, settings.allowed_processes)
    register_window_tools(registry)
    register_clipboard_tools(registry)
    reminder_store = ReminderStore(settings.database_path)
    register_reminder_tools(registry, reminder_store)
    router = CommandRouter(
        registry,
        allowed_apps,
        settings.allowed_processes,
        app_aliases,
        settings.wake_aliases,
    )

    profile_path = settings.workflows_path.parent / "ai_profile.json"
    profile_data: dict[str, Any] = {}
    if profile_path.is_file():
        try:
            loaded_profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if isinstance(loaded_profile, dict):
                profile_data = loaded_profile
        except (OSError, ValueError, json.JSONDecodeError):
            logging.warning("Saved AI profile is invalid; using config.toml defaults.")

    profile_enabled = bool(profile_data.get("enabled", settings.llm.enabled))
    profile_base_url = str(profile_data.get("base_url") or settings.llm.base_url).rstrip("/")
    profile_model = str(profile_data.get("model") or settings.llm.model)
    assistant = None
    if profile_enabled:
        provider = OpenAICompatibleProvider(
            profile_base_url,
            profile_model,
            settings.llm.api_key,
            settings.llm.timeout_seconds,
            settings.allow_remote_llm,
        )
        assistant = AssistantOrchestrator(
            provider, registry, settings.llm.system_prompt, settings.llm.max_tool_rounds
        )

    store = ChatStore(settings.database_path)
    if assistant is not None:
        assistant.history = store.recent_messages()
    workflow_library = WorkflowLibrary(settings.workflows_path)
    workflow_runner = WorkflowGraphRunner(registry)
    return (
        router, assistant, store, workflow_library, workflow_runner,
        registry, reminder_store, allowed_apps, profile_data
    )


def main() -> int:
    try:
        from PySide6.QtCore import QObject, QEasingCurve, QPropertyAnimation, Qt, QThread, QTimer, Signal, Slot
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices, QFont, QMovie, QPixmap
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QFileDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMessageBox,
            QPlainTextEdit,
            QScrollArea,
            QPushButton,
            QSplitter,
            QStackedLayout,
            QStackedWidget,
            QStyle,
            QSystemTrayIcon,
            QTabWidget,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
        from hellsaiz_pc_ai.workflows.qt_canvas import WorkflowCanvas
    except ImportError:
        print("PySide6 is missing. Run: pip install -e .")
        return 2

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    app = QApplication.instance() or QApplication([])
    instance_lock = SingleInstanceLock(settings.workflows_path.parent / "assistant.lock")
    if not instance_lock.acquire():
        QMessageBox.information(
            None,
            "Hellsaiz PC AI",
            "Помощник уже запущен. Используй открытое окно приложения.",
        )
        return 0
    atexit.register(instance_lock.release)

    (
        router, assistant, store, workflow_library, workflow_runner, registry,
        reminder_store, allowed_apps, profile_data
    ) = build_runtime(settings)
    active_voice = {"name": str(profile_data.get("voice_name") or settings.speech.tts_voice_name)}
    raw_recording_seconds = profile_data.get(
        "recording_seconds", settings.speech.recording_seconds
    )
    recording_seconds = (
        float(raw_recording_seconds)
        if isinstance(raw_recording_seconds, (int, float))
        and not isinstance(raw_recording_seconds, bool)
        and 1.0 <= float(raw_recording_seconds) <= 15.0
        else settings.speech.recording_seconds
    )
    active_stt = {
        "recording_seconds": recording_seconds,
        "primary": str(profile_data.get("stt_primary") or settings.speech.stt_primary),
        "fallback": str(profile_data.get("stt_fallback") or settings.speech.stt_fallback),
        "vosk_model_path": str(
            profile_data.get("vosk_model_path") or settings.speech.vosk_model_path
        ),
        "whisper_cpp_executable": str(
            profile_data.get("whisper_cpp_executable")
            or settings.speech.whisper_cpp_executable or ""
        ),
        "whisper_cpp_model": str(
            profile_data.get("whisper_cpp_model") or settings.speech.whisper_cpp_model or ""
        ),
    }
    active_microphone = {
        "name": str(profile_data.get("microphone_device") or "")
    }
    install_root = installed_app_root()
    current_app_version = installed_version(install_root, APP_VERSION)
    if install_root is not None:
        ensure_desktop_shortcut(install_root / "HellsaizLauncher.exe")

    window = QMainWindow()
    window.setWindowTitle(settings.app_name)
    window.resize(1240, 820)
    window.setMinimumSize(900, 640)
    wallpaper_store = WallpaperStore(settings.workflows_path.parent)
    wallpaper_movie = None
    wallpaper_layer = None

    class HotkeyBridge(QObject):
        activated = Signal(str, str)

    class HotkeyDispatcher(QObject):
        def __init__(self, callback: Any) -> None:
            super().__init__()
            self.callback = callback

        @Slot(str, str)
        def dispatch(self, workflow_id: str, combo: str) -> None:
            self.callback(workflow_id, combo)

    class VoskModelDownloadWorker(QThread):
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

    vosk_model_download_workers: list[VoskModelDownloadWorker] = []

    class WakeListenerWorker(QThread):
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

    wake_listener_state: dict[str, Any] = {"worker": None, "dispatcher": None}

    class Worker(QThread):
        completed = Signal(str, str)
        failed = Signal(str)

        def __init__(
            self,
            prompt: str,
            voice_input: bool,
            speak_reply: bool,
            workflow_trigger: WorkflowTrigger | None = None,
            stt_profile: dict[str, Any] | None = None,
            microphone_device: str = "",
            assistant_profile: dict[str, Any] | None = None,
            voice_name: str = "Aleksandr",
        ) -> None:
            super().__init__()
            self.prompt = prompt
            self.voice_input = voice_input
            self.speak_reply = speak_reply
            self.workflow_trigger = workflow_trigger
            self.stt_profile = dict(stt_profile or active_stt)
            self.microphone_device = microphone_device
            self.assistant_profile = dict(assistant_profile or profile_data)
            self.voice_name = voice_name

        def run(self) -> None:
            try:
                prompt = self.prompt
                if self.voice_input:
                    from hellsaiz_pc_ai.speech.capture import record_microphone
                    from hellsaiz_pc_ai.speech.factory import build_speech_router

                    with tempfile.NamedTemporaryFile(
                        prefix="hellsaiz-command-", suffix=".wav", delete=False
                    ) as audio_file:
                        audio_path = Path(audio_file.name)
                    try:
                        record_microphone(
                            audio_path,
                            duration_seconds=self.stt_profile["recording_seconds"],
                            device=self.microphone_device or None,
                        )
                        speech_router = build_speech_router(
                            primary=self.stt_profile["primary"],
                            fallback=self.stt_profile["fallback"],
                            vosk_model_path=Path(self.stt_profile["vosk_model_path"]),
                            whisper_executable=(
                                Path(self.stt_profile["whisper_cpp_executable"])
                                if self.stt_profile["whisper_cpp_executable"] else None
                            ),
                            whisper_model=(
                                Path(self.stt_profile["whisper_cpp_model"])
                                if self.stt_profile["whisper_cpp_model"] else None
                            ),
                        )
                        transcription = speech_router.transcribe(audio_path)
                        prompt = transcription.text
                        if transcription.fallback_used:
                            logging.warning(
                                "Speech recognition fell back to %s after %s",
                                transcription.engine,
                                transcription.fallback_reason,
                            )
                    finally:
                        audio_path.unlink(missing_ok=True)
                if self.workflow_trigger is None and not prompt.strip():
                    self.failed.emit("Команда не распознана.")
                    return

                answer = None
                try:
                    trigger = self.workflow_trigger or WorkflowTrigger("text", prompt)
                    for workflow_id, graph in workflow_library.list():
                        if trigger.workflow_id is not None and workflow_id != trigger.workflow_id:
                            continue
                        execution = workflow_runner.run(graph, trigger)
                        if execution.started:
                            lines = [
                                f"Сценарий «{graph.name}» ({workflow_id}): {execution.message}"
                            ]
                            lines.extend(f"• {step.output}" for step in execution.steps)
                            answer = "\n".join(lines)
                            break
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    logging.warning("Workflow library could not be fully loaded: %s", exc)

                if self.workflow_trigger is None:
                    if answer is None:
                        answer = router.route(prompt)
                    if answer is None and assistant is not None:
                        answer = assistant.reply(prompt)
                    if answer is None:
                        answer = (
                            "Эта фраза пока не входит в список локальных команд. "
                            "Введите «помощь», чтобы увидеть доступные команды. "
                            "Генеративный ИИ выключен."
                        )
                elif answer is None:
                    if self.workflow_trigger.workflow_id:
                        answer = (
                            f"Сценарий «{self.workflow_trigger.workflow_id}» больше не доступен "
                            "или его триггер был изменён. Ничего не запущено."
                        )
                    elif self.workflow_trigger.kind == "startup":
                        answer = "Не найден сценарий автозапуска. Ничего не запущено."
                    elif self.workflow_trigger.kind == "schedule":
                        answer = (
                            f"Для расписания {self.workflow_trigger.value} не найден сценарий. "
                            "Ничего не запущено."
                        )
                    else:
                        answer = (
                            f"Для комбинации {self.workflow_trigger.value} не найден "
                            "сценарий с таким триггером."
                        )

                if self.speak_reply:
                    try:
                        from hellsaiz_pc_ai.speech.output import SpeechOutputRouter
                        from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer

                        speakers = {
                            "sapi5": Sapi5Synthesizer(
                                self.voice_name,
                                settings.speech.tts_rate,
                                settings.speech.tts_volume,
                            )
                        }
                        voice_id = str(self.assistant_profile.get("piper_voice_id") or "")
                        voice_models = list_installed_voices(
                            settings.workflows_path.parent / "voices"
                        )
                        selected_model = next(
                            (voice for voice in voice_models if voice.voice_id == voice_id),
                            None,
                        )
                        if selected_model is not None:
                            speakers["piper"] = PiperSynthesizer(selected_model.model_path)
                        preferred_tts = str(self.assistant_profile.get("tts_engine") or "sapi5").casefold()
                        if preferred_tts not in {"sapi5", "piper"}:
                            preferred_tts = "sapi5"
                        fallback_tts = "sapi5" if preferred_tts == "piper" else "piper"
                        result = SpeechOutputRouter(
                            speakers, preferred_tts, fallback_tts
                        ).speak(answer)
                        if result.fallback_used:
                            logging.warning(
                                "TTS fell back to %s because the preferred engine failed: %s",
                                result.engine,
                                result.primary_error,
                            )
                    except Exception as exc:
                        logging.warning("Speech output unavailable: %s", exc)
                        answer += "\n\n[Не удалось воспроизвести голос. Проверь установленные голоса и модель.]"

                stored_prompt = (
                    prompt
                    if prompt
                    else f"[trigger {self.workflow_trigger.kind}: {self.workflow_trigger.value}]"
                )
                store.add_message("user", stored_prompt)
                store.add_message("assistant", answer)
                self.completed.emit(prompt, answer)
            except ProviderError as exc:
                self.failed.emit(str(exc))
            except Exception as exc:
                logging.exception("Command execution failed")
                self.failed.emit(str(exc))

    tabs = QTabWidget()
    tabs.setDocumentMode(True)

    home_page = QWidget()
    home_layout = QVBoxLayout(home_page)
    home_layout.setContentsMargins(28, 22, 28, 20)
    home_layout.setSpacing(12)

    header = QLabel(
        "<div style='font-size:10px; letter-spacing:3px; color:#858b95;'>HELLSAIZ</div>"
        "<div style='font-size:21px; font-weight:650; color:#f1f2f5;'>Чат</div>"
    )
    header.setStyleSheet("padding-bottom:5px;")
    home_layout.addWidget(header)

    transcript = QTextEdit()
    transcript.setReadOnly(True)
    transcript.setAcceptRichText(True)
    transcript.setPlaceholderText("Напишите сообщение или используйте голосовой ввод.")
    transcript.setFrameShape(QFrame.Shape.NoFrame)
    transcript.setStyleSheet(
        "QTextEdit { background:transparent; border:0; padding:18px 10px; "
        "font-size:14px; line-height:1.5; }"
    )
    home_layout.addWidget(transcript, 1)

    profile_panel = QFrame()
    profile_panel.setObjectName("profilePanel")
    profile_layout = QVBoxLayout(profile_panel)
    profile_layout.setContentsMargins(16, 14, 16, 14)
    profile_layout.setSpacing(10)

    profile_heading = QLabel("ПРОФИЛЬ ИИ И ГОЛОСА")
    profile_heading.setStyleSheet("color:#aeb4be; font-size:10px; letter-spacing:1.8px;")
    profile_layout.addWidget(profile_heading)

    provider_row = QHBoxLayout()
    provider_label = QLabel("Провайдер")
    provider_label.setMinimumWidth(95)
    provider_combo = QComboBox()
    provider_combo.addItem("LM Studio", "lm-studio")
    provider_combo.addItem("Ollama", "ollama")
    provider_combo.addItem("llama.cpp / другой", "custom")
    provider_combo.setMinimumWidth(180)
    endpoint_edit = QLineEdit()
    endpoint_edit.setPlaceholderText("Адрес локального OpenAI-совместимого сервера")
    endpoint_edit.setMinimumWidth(260)
    provider_row.addWidget(provider_label)
    provider_row.addWidget(provider_combo)
    provider_row.addWidget(endpoint_edit, 1)
    profile_layout.addLayout(provider_row)

    model_row = QHBoxLayout()
    model_label = QLabel("Модель")
    model_label.setMinimumWidth(95)
    model_edit = QLineEdit()
    model_edit.setPlaceholderText("Имя модели на выбранном сервере")
    ai_enabled_check = QCheckBox("Использовать ИИ как резерв для неизвестных фраз")
    model_row.addWidget(model_label)
    model_row.addWidget(model_edit, 1)
    model_row.addWidget(ai_enabled_check)
    profile_layout.addLayout(model_row)

    voice_row = QHBoxLayout()
    voice_label = QLabel("Голос ответа")
    voice_label.setMinimumWidth(95)
    voice_combo = QComboBox()
    voice_combo.setMinimumWidth(220)
    refresh_voices_button = QPushButton("Найти голоса")
    test_voice_button = QPushButton("Проверить")
    speak_toggle = QCheckBox("Озвучивать ответы")
    voice_row.addWidget(voice_label)
    voice_row.addWidget(voice_combo, 1)
    voice_row.addWidget(refresh_voices_button)
    voice_row.addWidget(test_voice_button)
    voice_row.addWidget(speak_toggle)
    profile_layout.addLayout(voice_row)

    profile_footer = QHBoxLayout()
    profile_status = QLabel("Параметры сохраняются локально.")
    profile_status.setStyleSheet("color:#89919d; font-size:11px;")
    profile_apply_button = QPushButton("Применить")
    profile_footer.addWidget(profile_status, 1)
    profile_footer.addWidget(profile_apply_button)
    profile_layout.addLayout(profile_footer)

    home_layout.addWidget(profile_panel)
    profile_panel.setMaximumHeight(0)
    profile_panel.setVisible(False)
    profile_animation = QPropertyAnimation(profile_panel, b"maximumHeight", window)
    profile_animation.setDuration(190)
    profile_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    profile_animation.finished.connect(
        lambda: profile_panel.setVisible(False)
        if profile_panel.maximumHeight() == 0 else None
    )

    controls = QHBoxLayout()
    controls.setSpacing(8)
    input_box = QLineEdit()
    input_box.setObjectName("chatComposer")
    input_box.setPlaceholderText("Спросите Hellsaiz…")
    input_box.setMinimumHeight(48)
    profile_button = QPushButton("ИИ / Голос  ⌃")
    profile_button.setObjectName("profileButton")
    profile_button.setMinimumHeight(46)
    voice_button = QPushButton("Микрофон")
    voice_button.setObjectName("voiceButton")
    voice_button.setMinimumHeight(46)
    send_button = QPushButton("Отправить")
    send_button.setObjectName("sendButton")
    send_button.setMinimumHeight(46)
    controls.addWidget(input_box, 1)
    controls.addWidget(voice_button)
    controls.addWidget(profile_button)
    controls.addWidget(send_button)
    home_layout.addLayout(controls)

    endpoint_defaults = {
        "lm-studio": "http://127.0.0.1:1234/v1",
        "ollama": "http://127.0.0.1:11434/v1",
        "custom": settings.llm.base_url,
    }
    saved_provider = str(profile_data.get("provider") or "lm-studio")
    provider_index = provider_combo.findData(saved_provider)
    if provider_index >= 0:
        provider_combo.setCurrentIndex(provider_index)
    endpoint_edit.setText(str(profile_data.get("base_url") or settings.llm.base_url))
    model_edit.setText(str(profile_data.get("model") or settings.llm.model))
    ai_enabled_check.setChecked(bool(profile_data.get("enabled", settings.llm.enabled)))
    speak_toggle.setChecked(bool(profile_data.get("auto_speak", settings.speech.auto_speak)))

    def provider_changed() -> None:
        provider = str(provider_combo.currentData() or "custom")
        if provider != "custom":
            endpoint_edit.setText(endpoint_defaults[provider])

    provider_combo.currentIndexChanged.connect(provider_changed)

    def toggle_profile_menu() -> None:
        profile_animation.stop()
        if not profile_panel.isVisible():
            profile_panel.setVisible(True)
            profile_panel.setMaximumHeight(0)
            profile_animation.setStartValue(0)
            profile_animation.setEndValue(profile_panel.sizeHint().height() + 12)
            profile_animation.start()
            profile_button.setText("ИИ / Голос  ⌄")
        else:
            profile_animation.setStartValue(profile_panel.height())
            profile_animation.setEndValue(0)
            profile_animation.start()
            profile_button.setText("ИИ / Голос  ⌃")

    profile_button.clicked.connect(toggle_profile_menu)

    def refresh_voices() -> None:
        try:
            from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer

            selected = active_voice["name"]
            voices = Sapi5Synthesizer().list_voices()
            voice_combo.clear()
            for voice in voices:
                voice_combo.addItem(voice.name, voice.id)
            index = voice_combo.findText(selected)
            if index >= 0:
                voice_combo.setCurrentIndex(index)
            voice_status_text = f"Найдено голосов Windows: {len(voices)}."
            if not voices:
                voice_status_text = "В Windows пока не найдено доступных голосов SAPI5."
            profile_status.setText(voice_status_text)
        except Exception as exc:
            profile_status.setText(f"Не удалось получить список SAPI5: {exc}")

    def test_voice() -> None:
        voice_name = voice_combo.currentText()
        if not voice_name:
            profile_status.setText("Сначала найди установленные голоса Windows.")
            return
        try:
            from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer

            Sapi5Synthesizer(
                voice_name, settings.speech.tts_rate, settings.speech.tts_volume
            ).speak("Hellsaiz PC AI. Проверка локального голоса.")
            profile_status.setText(f"Голос доступен: {voice_name}.")
        except Exception as exc:
            profile_status.setText(f"Не удалось воспроизвести голос: {exc}")

    refresh_voices_button.clicked.connect(refresh_voices)
    test_voice_button.clicked.connect(test_voice)

    def apply_profile() -> None:
        nonlocal assistant
        endpoint = endpoint_edit.text().strip().rstrip("/")
        model = model_edit.text().strip()
        enabled = ai_enabled_check.isChecked()
        if enabled and (not endpoint.startswith(("http://", "https://")) or not model):
            profile_status.setText("Укажи корректный адрес сервера и имя модели.")
            return
        if enabled:
            try:
                provider = OpenAICompatibleProvider(
                    endpoint,
                    model,
                    settings.llm.api_key,
                    settings.llm.timeout_seconds,
                    settings.allow_remote_llm,
                )
                assistant = AssistantOrchestrator(
                    provider, registry, settings.llm.system_prompt, settings.llm.max_tool_rounds
                )
                assistant.history = store.recent_messages()
            except Exception as exc:
                profile_status.setText(f"Не удалось применить ИИ-профиль: {exc}")
                return
        else:
            assistant = None

        selected_voice = voice_combo.currentText()
        if selected_voice:
            active_voice["name"] = selected_voice
        profile_data.update({
            "provider": str(provider_combo.currentData() or "custom"),
            "base_url": endpoint or settings.llm.base_url,
            "model": model or settings.llm.model,
            "enabled": enabled,
            "voice_name": active_voice["name"],
            "auto_speak": speak_toggle.isChecked(),
        })
        profile_path = settings.workflows_path.parent / "ai_profile.json"
        try:
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = profile_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(profile_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(profile_path)
            profile_status.setText("Профиль сохранён. Настройки применены.")
        except OSError as exc:
            profile_status.setText(f"Профиль применён, но не сохранён: {exc}")

    profile_apply_button.clicked.connect(apply_profile)
    refresh_voices()

    tabs.addTab(home_page, "Чат")

    reminder_page = QWidget()
    reminder_layout = QVBoxLayout(reminder_page)
    reminder_title = QLabel("НАПОМИНАНИЯ / ЛОКАЛЬНОЕ ХРАНИЛИЩЕ")
    reminder_title.setStyleSheet("font-size:18px; font-weight:650; color:#f1f2f4;")
    reminder_layout.addWidget(reminder_title)
    reminder_description = QLabel(
        "Записи хранятся локально. Они срабатывают, пока Hellsaiz PC AI запущен; "
        "просроченные напоминания будут показаны после следующего запуска."
    )
    reminder_description.setWordWrap(True)
    reminder_description.setStyleSheet("color:#aab0ba;")
    reminder_layout.addWidget(reminder_description)
    reminder_list = QListWidget()
    reminder_layout.addWidget(reminder_list, 1)
    reminder_buttons = QHBoxLayout()
    refresh_reminders_button = QPushButton("Обновить")
    dismiss_reminder_button = QPushButton("Отменить выбранное")
    reminder_buttons.addWidget(refresh_reminders_button)
    reminder_buttons.addWidget(dismiss_reminder_button)
    reminder_buttons.addStretch(1)
    reminder_layout.addLayout(reminder_buttons)
    reminder_status = QLabel("Напоминания сохраняются в локальной базе SQLite.")
    reminder_status.setStyleSheet("color:#aab0ba;")
    reminder_layout.addWidget(reminder_status)

    def refresh_reminder_list() -> None:
        reminder_list.clear()
        try:
            entries = reminder_store.list_pending()
        except (OSError, ValueError):
            logging.exception("Could not load reminders")
            reminder_status.setText("Не удалось загрузить напоминания.")
            return
        for reminder in entries:
            due_label = reminder.due_at.astimezone().strftime("%d.%m.%Y %H:%M:%S")
            item = QListWidgetItem(f"#{reminder.id}  ·  {due_label}  ·  {reminder.message}")
            item.setData(Qt.ItemDataRole.UserRole, reminder.id)
            reminder_list.addItem(item)
        reminder_status.setText(f"Активных напоминаний: {len(entries)}")

    def dismiss_selected_reminder() -> None:
        item = reminder_list.currentItem()
        if item is None:
            reminder_status.setText("Выбери напоминание для отмены.")
            return
        reminder_id = int(item.data(Qt.ItemDataRole.UserRole))
        if reminder_store.dismiss(reminder_id):
            reminder_status.setText(f"Напоминание #{reminder_id} отменено.")
        else:
            reminder_status.setText("Напоминание уже не активно.")
        refresh_reminder_list()

    refresh_reminders_button.clicked.connect(refresh_reminder_list)
    dismiss_reminder_button.clicked.connect(dismiss_selected_reminder)
    refresh_reminder_list()
    tabs.addTab(reminder_page, "Напоминания")

    # Scenario workspace: validated JSON graph + a live monochrome node-map preview.
    scenario_page = QWidget()
    scenario_layout = QVBoxLayout(scenario_page)
    scenario_title = QLabel("СЦЕНАРИИ / ВИЗУАЛЬНАЯ КАРТА")
    scenario_title.setStyleSheet("font-size:18px; font-weight:650; color:#f1f2f4;")
    scenario_layout.addWidget(scenario_title)
    scenario_hint = QLabel(
        "Перетаскивай узлы мышью, сохраняй их расположение и настраивай связи через JSON. "
        "Ctrl+Alt+H — пример запуска. Произвольный код не поддерживается."
    )
    scenario_hint.setStyleSheet("color:#aab0ba;")
    scenario_layout.addWidget(scenario_hint)

    scenario_workspace = QHBoxLayout()
    scenario_list = QListWidget()
    scenario_list.setMinimumWidth(190)
    scenario_workspace.addWidget(scenario_list, 1)

    scenario_splitter = QSplitter(Qt.Orientation.Horizontal)
    graph_view = WorkflowCanvas()
    graph_view.setMinimumWidth(360)
    scenario_splitter.addWidget(graph_view)
    graph_editor = QPlainTextEdit()
    graph_editor.setPlaceholderText("JSON-граф сценария…")
    graph_editor.setFont(QFont("Consolas", 10))
    scenario_splitter.addWidget(graph_editor)
    scenario_splitter.setStretchFactor(0, 1)
    scenario_splitter.setStretchFactor(1, 1)
    scenario_workspace.addWidget(scenario_splitter, 5)
    scenario_layout.addLayout(scenario_workspace, 1)

    builder_title = QLabel("КОНСТРУКТОР УЗЛОВ")
    builder_title.setStyleSheet("color:#c5cad2; font-size:11px; letter-spacing:1.5px;")
    scenario_layout.addWidget(builder_title)
    builder_row = QHBoxLayout()
    builder_source = QComboBox()
    builder_source.setMinimumWidth(120)
    builder_id = QLineEdit("new-action")
    builder_id.setPlaceholderText("id нового узла")
    builder_tool = QComboBox()
    registered_tool_names = []
    for tool_schema in registry.openai_schemas():
        function = tool_schema["function"]
        registered_tool_names.append(function["name"])
        builder_tool.addItem(function["name"], function["name"])
    builder_arguments = QLineEdit("{}")
    builder_arguments.setPlaceholderText('Аргументы JSON, например {"app":"notepad"}')
    add_tool_button = QPushButton("Добавить действие")
    builder_row.addWidget(builder_source)
    builder_row.addWidget(builder_id)
    builder_row.addWidget(builder_tool)
    builder_row.addWidget(builder_arguments, 2)
    builder_row.addWidget(add_tool_button)
    scenario_layout.addLayout(builder_row)

    condition_row = QHBoxLayout()
    wait_id = QLineEdit("wait-next")
    wait_id.setPlaceholderText("id ожидания")
    wait_seconds = QLineEdit("2")
    wait_seconds.setMaximumWidth(60)
    add_wait_button = QPushButton("Добавить ожидание")
    condition_id = QLineEdit("hour-check")
    condition_id.setPlaceholderText("id условия")
    condition_operator = QComboBox()
    for label, operator in [("час ≥", "gte"), ("час =", "eq"), ("час <", "lt"), ("час ≤", "lte"), ("час >", "gt")]:
        condition_operator.addItem(label, operator)
    condition_hour = QLineEdit("22")
    condition_hour.setMaximumWidth(45)
    add_condition_button = QPushButton("Добавить условие")
    condition_row.addWidget(wait_id)
    condition_row.addWidget(wait_seconds)
    condition_row.addWidget(add_wait_button)
    condition_row.addSpacing(8)
    condition_row.addWidget(condition_id)
    condition_row.addWidget(condition_operator)
    condition_row.addWidget(condition_hour)
    condition_row.addWidget(add_condition_button)
    scenario_layout.addLayout(condition_row)

    repeat_row = QHBoxLayout()
    repeat_id = QLineEdit("repeat-action")
    repeat_id.setPlaceholderText("id повтора")
    repeat_count = QLineEdit("3")
    repeat_count.setMaximumWidth(60)
    add_repeat_button = QPushButton("Повторить выбранное действие")
    repeat_hint = QLabel("Используется инструмент и JSON-аргументы из верхней строки.")
    repeat_hint.setStyleSheet("color:#9098a4; font-size:11px;")
    repeat_row.addWidget(repeat_id)
    repeat_row.addWidget(repeat_count)
    repeat_row.addWidget(add_repeat_button)
    repeat_row.addWidget(repeat_hint, 1)
    scenario_layout.addLayout(repeat_row)

    weekday_row = QHBoxLayout()
    weekday_id = QLineEdit("weekday-check")
    weekday_id.setPlaceholderText("id дня недели")
    weekday_value = QComboBox()
    for day_name, day_number in [
        ("Понедельник", 1), ("Вторник", 2), ("Среда", 3), ("Четверг", 4),
        ("Пятница", 5), ("Суббота", 6), ("Воскресенье", 7),
    ]:
        weekday_value.addItem(day_name, day_number)
    add_weekday_button = QPushButton("Добавить условие дня")
    weekday_row.addWidget(weekday_id)
    weekday_row.addWidget(weekday_value)
    weekday_row.addWidget(add_weekday_button)
    weekday_row.addStretch(1)
    scenario_layout.addLayout(weekday_row)

    scenario_id = QLineEdit()
    scenario_id.setPlaceholderText("id-сценария, например night-mode")
    scenario_layout.addWidget(scenario_id)
    scenario_buttons = QHBoxLayout()
    new_scenario_button = QPushButton("Новый")
    new_hotkey_scenario_button = QPushButton("Пример hotkey")
    new_schedule_scenario_button = QPushButton("Пример расписания")
    new_startup_scenario_button = QPushButton("Пример автозапуска")
    validate_scenario_button = QPushButton("Проверить граф")
    save_scenario_button = QPushButton("Сохранить")
    delete_scenario_button = QPushButton("Удалить")
    run_scenario_button = QPushButton("Запустить сейчас")
    fit_graph_button = QPushButton("По размеру")
    reset_layout_button = QPushButton("Сбросить расположение")
    scenario_buttons.addWidget(fit_graph_button)
    scenario_buttons.addWidget(reset_layout_button)
    scenario_buttons.addWidget(new_scenario_button)
    scenario_buttons.addWidget(new_hotkey_scenario_button)
    scenario_buttons.addWidget(new_schedule_scenario_button)
    scenario_buttons.addWidget(new_startup_scenario_button)
    scenario_buttons.addWidget(validate_scenario_button)
    scenario_buttons.addWidget(save_scenario_button)
    scenario_buttons.addWidget(run_scenario_button)
    scenario_buttons.addWidget(delete_scenario_button)
    scenario_layout.addLayout(scenario_buttons)
    scenario_status = QLabel("Сценарии хранятся локально в JSON.")
    scenario_status.setStyleSheet("color:#aab0ba;")
    scenario_layout.addWidget(scenario_status)

    def render_graph(
        graph: WorkflowGraph, workflow_id: str | None = None, preserve: bool = False
    ) -> None:
        positions = workflow_library.load_layout(workflow_id) if workflow_id else {}
        if preserve:
            positions.update(graph_view.export_layout())
        graph_view.set_graph(graph, positions)

    def refresh_scenario_list() -> None:
        scenario_list.clear()
        try:
            entries = workflow_library.list()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            scenario_status.setText(f"Ошибка чтения библиотеки: {exc}")
            return
        for workflow_id, graph in entries:
            item = f"{graph.name}  ·  {workflow_id}"
            scenario_list.addItem(item)
            scenario_list.item(scenario_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, workflow_id
            )
        scenario_status.setText(f"Локальных сценариев: {len(entries)}")

    def load_selected_scenario() -> None:
        item = scenario_list.currentItem()
        if item is None:
            return
        workflow_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            graph = workflow_library.load(workflow_id)
            scenario_id.setText(workflow_id)
            graph_editor.setPlainText(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2))
            render_graph(graph, workflow_id)
            refresh_builder_sources(graph)
            scenario_status.setText(f"Загружен сценарий: {graph.name}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            scenario_status.setText(f"Не удалось загрузить сценарий: {exc}")

    def create_scenario() -> None:
        example = {
            "name": "Ночной режим",
            "nodes": [
                {"id": "start", "type": "trigger.text", "config": {"phrase": "ночной режим"}},
                {"id": "hour", "type": "condition.hour", "config": {"operator": "gte", "value": 22}},
                {"id": "night", "type": "action.tool", "config": {"name": "set_volume", "arguments": {"percent": 30}}},
                {"id": "day", "type": "action.tool", "config": {"name": "set_volume", "arguments": {"percent": 60}}},
            ],
            "edges": [
                {"from": "start", "to": "hour"},
                {"from": "hour", "to": "night", "when": "true"},
                {"from": "hour", "to": "day", "when": "false"},
            ],
        }
        scenario_id.setText("night-mode")
        graph_editor.setPlainText(json.dumps(example, ensure_ascii=False, indent=2))
        try:
            example_graph = WorkflowGraph.from_dict(example)
            render_graph(example_graph)
            refresh_builder_sources(example_graph)
            scenario_status.setText("Пример создан. Проверь и сохрани его.")
        except ValueError as exc:
            scenario_status.setText(str(exc))

    def create_schedule_scenario() -> None:
        example = {
            "name": "Ежедневная проверка времени",
            "nodes": [
                {
                    "id": "start",
                    "type": "trigger.schedule",
                    "config": {"time": "09:00", "days": [1, 2, 3, 4, 5, 6, 7]},
                },
                {
                    "id": "time",
                    "type": "action.tool",
                    "config": {"name": "get_local_time", "arguments": {}},
                },
            ],
            "edges": [{"from": "start", "to": "time"}],
        }
        scenario_id.setText("daily-time-check")
        graph_editor.setPlainText(json.dumps(example, ensure_ascii=False, indent=2))
        try:
            example_graph = WorkflowGraph.from_dict(example)
            render_graph(example_graph)
            refresh_builder_sources(example_graph)
            scenario_status.setText(
                "Пример расписания создан. Измени время и дни в JSON, затем сохрани."
            )
        except ValueError as exc:
            scenario_status.setText(str(exc))

    def create_startup_scenario() -> None:
        example = {
            "name": "Проверка при запуске",
            "nodes": [
                {"id": "start", "type": "trigger.startup", "config": {}},
                {
                    "id": "time",
                    "type": "action.tool",
                    "config": {"name": "get_local_time", "arguments": {}},
                },
            ],
            "edges": [{"from": "start", "to": "time"}],
        }
        scenario_id.setText("startup-check")
        graph_editor.setPlainText(json.dumps(example, ensure_ascii=False, indent=2))
        try:
            example_graph = WorkflowGraph.from_dict(example)
            render_graph(example_graph)
            refresh_builder_sources(example_graph)
            scenario_status.setText(
                "Пример автозапуска создан. Сохрани его; запуск произойдёт при старте приложения."
            )
        except ValueError as exc:
            scenario_status.setText(str(exc))

    def create_hotkey_scenario() -> None:
        example = {
            "name": "Горячая клавиша — громкость",
            "nodes": [
                {"id": "start", "type": "trigger.hotkey", "config": {"hotkey": "Ctrl+Alt+H"}},
                {
                    "id": "volume",
                    "type": "action.tool",
                    "config": {"name": "set_volume", "arguments": {"percent": 35}},
                },
            ],
            "edges": [{"from": "start", "to": "volume"}],
        }
        scenario_id.setText("hotkey-volume")
        graph_editor.setPlainText(json.dumps(example, ensure_ascii=False, indent=2))
        try:
            example_graph = WorkflowGraph.from_dict(example)
            render_graph(example_graph)
            refresh_builder_sources(example_graph)
            scenario_status.setText(
                "Пример создан. Сохрани его; Ctrl+Alt+H будет запускать действие автоматически."
            )
        except ValueError as exc:
            scenario_status.setText(str(exc))

    def refresh_builder_sources(graph: WorkflowGraph | None = None) -> None:
        try:
            current = graph or WorkflowGraph.from_dict(json.loads(graph_editor.toPlainText()))
            selected = builder_source.currentData()
            builder_source.clear()
            for node_id in terminal_nodes(current):
                builder_source.addItem(node_id, node_id)
            if selected is not None:
                index = builder_source.findData(selected)
                if index >= 0:
                    builder_source.setCurrentIndex(index)
        except (ValueError, json.JSONDecodeError):
            builder_source.clear()

    def apply_builder_graph(updated: WorkflowGraph) -> None:
        graph_editor.setPlainText(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2))
        render_graph(updated, scenario_id.text().strip() or None, preserve=True)
        refresh_builder_sources(updated)
        scenario_status.setText(
            f"Добавлен узел. В графе {len(updated.nodes)} узлов и {len(updated.edges)} связей."
        )

    def add_tool_node() -> None:
        try:
            graph = WorkflowGraph.from_dict(json.loads(graph_editor.toPlainText()))
            source_id = builder_source.currentData()
            if not source_id:
                raise ValueError("Выбери конечный узел ветви.")
            arguments = json.loads(builder_arguments.text() or "{}")
            updated = append_tool_action(
                graph, str(source_id), builder_id.text().strip(),
                str(builder_tool.currentData() or ""), arguments, set(registered_tool_names)
            )
            apply_builder_graph(updated)
            builder_id.setText("new-action")
        except (ValueError, json.JSONDecodeError) as exc:
            scenario_status.setText(f"Не удалось добавить действие: {exc}")

    def add_wait_node() -> None:
        try:
            graph = WorkflowGraph.from_dict(json.loads(graph_editor.toPlainText()))
            source_id = builder_source.currentData()
            if not source_id:
                raise ValueError("Выбери конечный узел ветви.")
            seconds = float(wait_seconds.text().replace(",", "."))
            updated = append_wait_action(graph, str(source_id), wait_id.text().strip(), seconds)
            apply_builder_graph(updated)
            wait_id.setText("wait-next")
        except (ValueError, json.JSONDecodeError) as exc:
            scenario_status.setText(f"Не удалось добавить ожидание: {exc}")

    def add_weekday_condition_node() -> None:
        try:
            graph = WorkflowGraph.from_dict(json.loads(graph_editor.toPlainText()))
            source_id = builder_source.currentData()
            if not source_id:
                raise ValueError("Выбери конечный узел ветви.")
            updated = append_weekday_condition(
                graph,
                str(source_id),
                weekday_id.text().strip(),
                int(weekday_value.currentData()),
            )
            apply_builder_graph(updated)
            weekday_id.setText("weekday-check")
        except (ValueError, json.JSONDecodeError) as exc:
            scenario_status.setText(f"Не удалось добавить условие дня недели: {exc}")

    def add_repeat_node() -> None:
        try:
            graph = WorkflowGraph.from_dict(json.loads(graph_editor.toPlainText()))
            source_id = builder_source.currentData()
            if not source_id:
                raise ValueError("Выбери конечный узел ветви.")
            arguments = json.loads(builder_arguments.text() or "{}")
            count = int(repeat_count.text())
            updated = append_repeat_action(
                graph,
                str(source_id),
                repeat_id.text().strip(),
                str(builder_tool.currentData() or ""),
                arguments,
                count,
                set(registered_tool_names),
            )
            apply_builder_graph(updated)
            repeat_id.setText("repeat-action")
        except (ValueError, json.JSONDecodeError) as exc:
            scenario_status.setText(f"Не удалось добавить повтор: {exc}")

    def add_condition_node() -> None:
        try:
            graph = WorkflowGraph.from_dict(json.loads(graph_editor.toPlainText()))
            source_id = builder_source.currentData()
            if not source_id:
                raise ValueError("Выбери конечный узел ветви.")
            updated = append_hour_condition(
                graph, str(source_id), condition_id.text().strip(),
                str(condition_operator.currentData()), int(condition_hour.text())
            )
            apply_builder_graph(updated)
            condition_id.setText("hour-check")
        except (ValueError, json.JSONDecodeError) as exc:
            scenario_status.setText(f"Не удалось добавить условие: {exc}")

    add_tool_button.clicked.connect(add_tool_node)
    add_wait_button.clicked.connect(add_wait_node)
    add_condition_button.clicked.connect(add_condition_node)
    add_repeat_button.clicked.connect(add_repeat_node)
    add_weekday_button.clicked.connect(add_weekday_condition_node)
    refresh_builder_sources()

    def validate_scenario() -> WorkflowGraph | None:
        try:
            graph = WorkflowGraph.from_dict(json.loads(graph_editor.toPlainText()))
            render_graph(graph, scenario_id.text().strip() or None, preserve=True)
            refresh_builder_sources(graph)
            scenario_status.setText(
                f"Граф корректен: {len(graph.nodes)} узлов, {len(graph.edges)} связей."
            )
            return graph
        except (ValueError, json.JSONDecodeError) as exc:
            scenario_status.setText(f"Граф не прошёл проверку: {exc}")
            return None

    def save_scenario() -> None:
        graph = validate_scenario()
        workflow_id = scenario_id.text().strip()
        if graph is None:
            return
        if not workflow_id:
            scenario_status.setText("Укажи id сценария.")
            return
        try:
            workflow_library.save(workflow_id, graph)
            workflow_library.save_layout(workflow_id, graph_view.export_layout())
            refresh_scenario_list()
            refresh_hotkey_service()
            scenario_status.setText(f"Сценарий «{graph.name}» сохранён локально.")
        except (OSError, ValueError) as exc:
            scenario_status.setText(f"Не удалось сохранить: {exc}")

    def delete_scenario() -> None:
        item = scenario_list.currentItem()
        if item is None:
            return
        workflow_id = item.data(Qt.ItemDataRole.UserRole)
        workflow_library.delete(workflow_id)
        refresh_scenario_list()
        refresh_hotkey_service()
        scenario_status.setText(f"Сценарий {workflow_id} удалён.")

    def run_selected_scenario() -> None:
        workflow_id = scenario_id.text().strip()
        if not workflow_id:
            scenario_status.setText("Сначала выбери или сохрани сценарий.")
            return
        try:
            graph = workflow_library.load(workflow_id)
            root = next(node for node in graph.nodes if node.kind.startswith("trigger."))
            trigger_kind = root.kind.removeprefix("trigger.")
            trigger_value = {
                "text": root.config.get("phrase", ""),
                "hotkey": root.config.get("hotkey", ""),
                "schedule": root.config.get("time", ""),
                "startup": "",
            }[trigger_kind]
        except (OSError, ValueError, KeyError, StopIteration, json.JSONDecodeError) as exc:
            scenario_status.setText(f"Не удалось подготовить сценарий: {exc}")
            return

        start_worker(
            workflow_trigger=WorkflowTrigger(trigger_kind, trigger_value, workflow_id)
        )

    new_scenario_button.clicked.connect(create_scenario)
    new_hotkey_scenario_button.clicked.connect(create_hotkey_scenario)
    new_schedule_scenario_button.clicked.connect(create_schedule_scenario)
    new_startup_scenario_button.clicked.connect(create_startup_scenario)
    validate_scenario_button.clicked.connect(validate_scenario)
    save_scenario_button.clicked.connect(save_scenario)
    delete_scenario_button.clicked.connect(delete_scenario)
    run_scenario_button.clicked.connect(run_selected_scenario)
    fit_graph_button.clicked.connect(graph_view.fit_graph)
    reset_layout_button.clicked.connect(graph_view.reset_layout)
    scenario_list.itemSelectionChanged.connect(load_selected_scenario)
    refresh_scenario_list()
    tabs.addTab(scenario_page, "Сценарии")

    apps_page = QWidget()
    apps_layout = QVBoxLayout(apps_page)
    apps_layout.setContentsMargins(22, 20, 22, 20)
    apps_title = QLabel("ПРИЛОЖЕНИЯ")
    apps_title.setStyleSheet("font-size:18px; font-weight:650; color:#f1f2f4;")
    apps_layout.addWidget(apps_title)
    apps_hint = QLabel(
        "Автопоиск использует ярлыки меню «Пуск» и записи Windows. "
        "Портативные приложения можно добавить вручную с любого диска. "
        "Полный фоновый обход всех дисков не выполняется."
    )
    apps_hint.setWordWrap(True)
    apps_hint.setStyleSheet("color:#929aa6;")
    apps_layout.addWidget(apps_hint)
    apps_list = QListWidget()
    apps_layout.addWidget(apps_list, 1)
    apps_buttons = QHBoxLayout()
    detect_apps_button = QPushButton("Найти установленные")
    add_executable_button = QPushButton("Добавить .exe / ярлык")
    register_app_button = QPushButton("Добавить выбранное")
    apps_buttons.addWidget(detect_apps_button)
    apps_buttons.addWidget(add_executable_button)
    apps_buttons.addWidget(register_app_button)
    apps_layout.addLayout(apps_buttons)
    apps_status = QLabel("Каталог приложений хранится локально.")
    apps_status.setStyleSheet("color:#929aa6;")
    apps_layout.addWidget(apps_status)

    catalog_path = settings.workflows_path.parent / "apps.json"
    discovered_candidates: list[AppCandidate] = []

    def refresh_apps_list() -> None:
        apps_list.clear()
        try:
            configured = load_user_catalog(catalog_path)
        except ValueError as exc:
            apps_status.setText(str(exc))
            configured = []
        for item in configured:
            row = QListWidgetItem(f"✓  {item['name']}  ·  {item['path']}")
            row.setData(Qt.ItemDataRole.UserRole, {"configured": True, "key": item["key"]})
            apps_list.addItem(row)
        for candidate in discovered_candidates:
            row = QListWidgetItem(f"{candidate.name}  ·  {candidate.path}")
            row.setData(Qt.ItemDataRole.UserRole, {
                "configured": False,
                "name": candidate.name,
                "path": str(candidate.path),
                "launch_kind": candidate.launch_kind,
            })
            apps_list.addItem(row)
        apps_status.setText(
            f"В каталоге: {len(configured)}. Найдено кандидатов: {len(discovered_candidates)}."
        )

    def detect_apps() -> None:
        nonlocal discovered_candidates
        try:
            discovered_candidates = discover_windows_apps()
            refresh_apps_list()
            if not discovered_candidates:
                apps_status.setText(
                    "Автопоиск не нашёл приложений. Добавь портативную программу через выбор файла."
                )
        except Exception as exc:
            apps_status.setText(f"Не удалось выполнить поиск: {exc}")

    def register_app_candidate(candidate: AppCandidate) -> None:
        try:
            existing = load_user_catalog(catalog_path)
            entry = add_candidate(catalog_path, candidate, existing)
            custom_apps = load_user_catalog(catalog_path)
            custom_allowed, custom_aliases = catalog_mappings(custom_apps)
            allowed_apps.update(custom_allowed)
            router.allowed_apps.update(custom_allowed)
            for key, phrases in custom_aliases.items():
                for phrase in (key, *phrases):
                    normalized = router._normalize_phrase(phrase)
                    owner = router.app_alias_lookup.get(normalized)
                    if owner is None or owner == key:
                        router.app_alias_lookup[normalized] = key
            refresh_apps_list()
            apps_status.setText(
                f"Добавлено: {entry['name']}. Теперь можно сказать «открой {entry['name']}»."
            )
        except (OSError, ValueError) as exc:
            apps_status.setText(f"Не удалось добавить приложение: {exc}")

    def add_selected_app() -> None:
        item = apps_list.currentItem()
        if item is None:
            apps_status.setText("Сначала выбери найденное приложение.")
            return
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        if data.get("configured"):
            apps_status.setText("Это приложение уже добавлено.")
            return
        try:
            candidate = AppCandidate(
                str(data["name"]), Path(str(data["path"])), str(data["launch_kind"])
            )
            register_app_candidate(candidate)
        except (KeyError, ValueError) as exc:
            apps_status.setText(f"Не удалось добавить приложение: {exc}")

    def browse_app() -> None:
        selected, _ = QFileDialog.getOpenFileName(
            window,
            "Выбрать приложение с любого диска",
            str(Path.home()),
            "Приложения Windows (*.exe *.lnk)",
        )
        if not selected:
            return
        path = Path(selected)
        kind = "shortcut" if path.suffix.casefold() == ".lnk" else "exe"
        register_app_candidate(AppCandidate(path.stem, path, kind))

    detect_apps_button.clicked.connect(detect_apps)
    register_app_button.clicked.connect(add_selected_app)
    add_executable_button.clicked.connect(browse_app)
    refresh_apps_list()
    tabs.addTab(apps_page, "Приложения")


    # Personal wallpaper library: no selected file means a completely black background.
    wallpaper_page = QWidget()
    wallpaper_layout = QVBoxLayout(wallpaper_page)
    wallpaper_layout.setContentsMargins(28, 24, 28, 24)
    wallpaper_layout.setSpacing(14)
    wallpaper_title = QLabel("ОБОИ")
    wallpaper_title.setStyleSheet("font-size:24px; font-weight:650; color:#eef2f7;")
    wallpaper_layout.addWidget(wallpaper_title)
    wallpaper_description = QLabel(
        "Выбери статичное изображение или GIF для фона приложения. "
        "Файл хранится только на этом компьютере. По умолчанию используется чистый чёрный фон."
    )
    wallpaper_description.setWordWrap(True)
    wallpaper_description.setStyleSheet("color:#aab3c0;")
    wallpaper_layout.addWidget(wallpaper_description)

    wallpaper_preview = QFrame()
    wallpaper_preview.setObjectName("wallpaperPreview")
    wallpaper_preview.setMinimumHeight(210)
    wallpaper_preview_layout = QVBoxLayout(wallpaper_preview)
    wallpaper_preview_layout.setContentsMargins(22, 20, 22, 20)
    wallpaper_preview_title = QLabel("ПРЕДПРОСМОТР")
    wallpaper_preview_title.setStyleSheet("color:#aeb7c4; font-size:10px; letter-spacing:1.8px;")
    wallpaper_preview_layout.addWidget(wallpaper_preview_title)
    wallpaper_status = QLabel("Используется чистый чёрный фон.")
    wallpaper_status.setWordWrap(True)
    wallpaper_status.setStyleSheet("color:#e6ecf4; font-size:15px;")
    wallpaper_preview_layout.addWidget(wallpaper_status)
    wallpaper_preview_layout.addStretch(1)
    wallpaper_layout.addWidget(wallpaper_preview)
    wallpaper_actions = QHBoxLayout()
    choose_wallpaper_button = QPushButton("Выбрать изображение / GIF")
    choose_wallpaper_button.setObjectName("primaryButton")
    clear_wallpaper_button = QPushButton("Сбросить на чёрный фон")
    wallpaper_actions.addWidget(choose_wallpaper_button)
    wallpaper_actions.addWidget(clear_wallpaper_button)
    wallpaper_layout.addLayout(wallpaper_actions)
    wallpaper_limit = QLabel("Форматы: PNG, JPG, WEBP, BMP, GIF · максимум 100 МБ")
    wallpaper_limit.setStyleSheet("color:#8e98a6; font-size:11px;")
    wallpaper_layout.addWidget(wallpaper_limit)

    def persist_wallpaper_status() -> None:
        selected_wallpaper = wallpaper_store.active_wallpaper()
        if selected_wallpaper is None:
            wallpaper_status.setText("Используется чистый чёрный фон.")
        else:
            kind = "Анимированные GIF-обои" if selected_wallpaper.suffix.lower() == ".gif" else "Статичные обои"
            wallpaper_status.setText(
                f"{kind}: {selected_wallpaper.name}\n"
                f"Размер: {selected_wallpaper.stat().st_size / (1024 * 1024):.1f} МБ"
            )

    def choose_wallpaper() -> None:
        selected, _ = QFileDialog.getOpenFileName(
            window,
            "Выбрать фон Hellsaiz PC AI",
            str(Path.home()),
            "Изображения и анимация (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not selected:
            return
        try:
            wallpaper_store.import_wallpaper(Path(selected))
            apply_wallpaper()
            persist_wallpaper_status()
        except (OSError, ValueError, WallpaperError) as exc:
            QMessageBox.warning(window, "Не удалось установить обои", str(exc))

    def clear_wallpaper() -> None:
        try:
            wallpaper_store.clear()
            apply_wallpaper()
            persist_wallpaper_status()
        except OSError as exc:
            QMessageBox.warning(window, "Не удалось сбросить обои", str(exc))

    choose_wallpaper_button.clicked.connect(choose_wallpaper)
    clear_wallpaper_button.clicked.connect(clear_wallpaper)
    persist_wallpaper_status()
    tabs.addTab(wallpaper_page, "Обои")

    # Piper voice library. Downloads happen in a worker thread and remain local.
    voices_page = QWidget()
    voices_layout = QVBoxLayout(voices_page)
    voices_layout.setContentsMargins(28, 24, 28, 24)
    voices_layout.setSpacing(12)
    voices_title = QLabel("БИБЛИОТЕКА ГОЛОСОВ")
    voices_title.setStyleSheet("font-size:24px; font-weight:650; color:#eef2f7;")
    voices_layout.addWidget(voices_title)
    voices_description = QLabel(
        "Локальные нейросетевые голоса Piper. Скачанная модель работает без интернета. "
        "Условия лицензии отличаются у разных голосов — перед использованием открой MODEL_CARD."
    )
    voices_description.setWordWrap(True)
    voices_description.setStyleSheet("color:#aab3c0;")
    voices_layout.addWidget(voices_description)

    voice_library_dir = settings.workflows_path.parent / "voices"
    voice_catalog = QComboBox()
    voice_catalog.addItem("Русский · Denis · medium", "ru_RU-denis-medium")
    voice_catalog.addItem("Русский · Dmitri · medium", "ru_RU-dmitri-medium")
    voice_catalog.addItem("Русский · Irina · medium (лицензия уточняется)", "ru_RU-irina-medium")
    voice_catalog.addItem("Русский · Ruslan · medium (CC BY-NC-SA 4.0)", "ru_RU-ruslan-medium")
    voice_catalog.setEditable(True)
    voice_catalog.setCurrentIndex(0)
    voice_download_row = QHBoxLayout()
    voice_download_row.addWidget(voice_catalog, 1)
    download_voice_button = QPushButton("Загрузить голос")
    download_voice_button.setObjectName("primaryButton")
    voice_download_row.addWidget(download_voice_button)
    voices_layout.addLayout(voice_download_row)

    installed_voices_list = QListWidget()
    voices_layout.addWidget(installed_voices_list, 1)
    voice_actions = QHBoxLayout()
    use_voice_button = QPushButton("Использовать для помощника")
    use_voice_button.setObjectName("primaryButton")
    test_piper_voice_button = QPushButton("Прослушать")
    use_system_voice_button = QPushButton("Использовать голос Windows")
    voice_actions.addWidget(use_voice_button)
    voice_actions.addWidget(test_piper_voice_button)
    voice_actions.addWidget(use_system_voice_button)
    voices_layout.addLayout(voice_actions)
    voices_status = QLabel(
        "Голоса ещё не загружены. Русские модели medium обычно занимают около 60–70 МБ."
    )
    voices_status.setWordWrap(True)
    voices_status.setStyleSheet("color:#9ca7b5;")
    voices_layout.addWidget(voices_status)

    voice_download_workers: list[QThread] = []

    class VoiceDownloadWorker(QThread):
        completed = Signal(object)
        failed = Signal(str)

        def __init__(self, voice_id: str) -> None:
            super().__init__()
            self.voice_id = voice_id

        def run(self) -> None:
            try:
                result = download_voice(self.voice_id, voice_library_dir)
                self.completed.emit(result)
            except (VoiceLibraryError, OSError, ValueError) as exc:
                self.failed.emit(str(exc))
            except Exception as exc:
                logging.exception("Piper voice download failed")
                self.failed.emit(f"Ошибка загрузки голоса: {exc}")

    def refresh_voice_library() -> None:
        installed_voices_list.clear()
        for voice in list_installed_voices(voice_library_dir):
            item = QListWidgetItem(
                f"{voice.voice_id}  ·  {voice.language}  ·  лицензия: {voice.license}"
            )
            item.setData(Qt.ItemDataRole.UserRole, voice.voice_id)
            installed_voices_list.addItem(item)
        selected_id = str(profile_data.get("piper_voice_id") or "")
        for index in range(installed_voices_list.count()):
            item = installed_voices_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == selected_id:
                installed_voices_list.setCurrentItem(item)
                break
        if installed_voices_list.count() == 0:
            voices_status.setText("Библиотека пуста. Выбери русский голос выше и нажми «Загрузить голос».")
        else:
            voices_status.setText(
                f"Установлено голосов: {installed_voices_list.count()}. "
                "Модели доступны локально после загрузки."
            )

    def download_selected_voice() -> None:
        voice_id = str(voice_catalog.currentData() or voice_catalog.currentText()).strip()
        if not voice_id:
            voices_status.setText("Выбери идентификатор голоса.")
            return
        if any(worker.isRunning() for worker in voice_download_workers):
            voices_status.setText("Дождись завершения текущей загрузки.")
            return
        download_voice_button.setEnabled(False)
        voices_status.setText(f"Загружаю {voice_id}: модель, конфигурацию и MODEL_CARD…")
        worker = VoiceDownloadWorker(voice_id)
        voice_download_workers.append(worker)

        def downloaded(voice: Any) -> None:
            refresh_voice_library()
            voices_status.setText(
                f"Голос {voice.voice_id} установлен. Лицензия в MODEL_CARD: {voice.license}"
            )

        def failed(message: str) -> None:
            voices_status.setText(message)

        worker.completed.connect(downloaded)
        worker.failed.connect(failed)
        worker.finished.connect(lambda: download_voice_button.setEnabled(True))
        worker.finished.connect(
            lambda: voice_download_workers.remove(worker)
            if worker in voice_download_workers else None
        )
        worker.start()

    def save_voice_profile(engine: str, voice_id: str | None = None) -> None:
        profile_data["tts_engine"] = engine
        if voice_id:
            profile_data["piper_voice_id"] = voice_id
        profile_path = settings.workflows_path.parent / "ai_profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = profile_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(profile_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(profile_path)

    def use_selected_piper_voice() -> None:
        item = installed_voices_list.currentItem()
        if item is None:
            voices_status.setText("Сначала выбери установленную модель.")
            return
        voice_id = str(item.data(Qt.ItemDataRole.UserRole))
        try:
            save_voice_profile("piper", voice_id)
            voices_status.setText(f"Для ответов помощника выбран Piper: {voice_id}.")
        except OSError as exc:
            voices_status.setText(f"Не удалось сохранить голос: {exc}")

    def test_selected_piper_voice() -> None:
        item = installed_voices_list.currentItem()
        if item is None:
            voices_status.setText("Сначала выбери установленную модель.")
            return
        voice_id = str(item.data(Qt.ItemDataRole.UserRole))
        model = voice_library_dir / f"{voice_id}.onnx"
        try:
            PiperSynthesizer(model).speak(
                "Привет. Я Хеллсайз. Проверка установленного голоса завершена."
            )
            voices_status.setText(f"Голос {voice_id} воспроизведён.")
        except Exception as exc:
            voices_status.setText(f"Не удалось проверить голос: {exc}")

    def use_windows_voice() -> None:
        try:
            save_voice_profile("sapi5")
            voices_status.setText("Для ответов помощника выбран системный голос Windows SAPI5.")
        except OSError as exc:
            voices_status.setText(f"Не удалось сохранить настройку: {exc}")

    download_voice_button.clicked.connect(download_selected_voice)
    use_voice_button.clicked.connect(use_selected_piper_voice)
    test_piper_voice_button.clicked.connect(test_selected_piper_voice)
    use_system_voice_button.clicked.connect(use_windows_voice)
    refresh_voice_library()
    tabs.addTab(voices_page, "Голоса")

    settings_page = QWidget()
    settings_layout = QVBoxLayout(settings_page)
    settings_layout.setContentsMargins(22, 20, 22, 20)
    settings_layout.setSpacing(12)
    settings_title = QLabel("НАСТРОЙКИ")
    settings_title.setStyleSheet("font-size:18px; font-weight:650; color:#f1f2f4;")
    settings_layout.addWidget(settings_title)
    settings_layout.addWidget(QLabel(f"История: {settings.database_path}"))
    settings_layout.addWidget(QLabel(f"Сценарии: {settings.workflows_path}"))

    speech_title = QLabel("РАСПОЗНАВАНИЕ РЕЧИ")
    speech_title.setStyleSheet("color:#c8cdd5; font-size:11px; letter-spacing:1.6px;")
    settings_layout.addWidget(speech_title)

    stt_engine_row = QHBoxLayout()
    stt_primary_combo = QComboBox()
    stt_primary_combo.addItem("Vosk · офлайн", "vosk")
    stt_primary_combo.addItem("Whisper.cpp · офлайн", "whisper.cpp")
    stt_fallback_combo = QComboBox()
    stt_fallback_combo.addItem("Без резерва", "none")
    stt_fallback_combo.addItem("Vosk", "vosk")
    stt_fallback_combo.addItem("Whisper.cpp", "whisper.cpp")
    stt_engine_row.addWidget(QLabel("Основной движок"))
    stt_engine_row.addWidget(stt_primary_combo, 1)
    stt_engine_row.addWidget(QLabel("Резервный"))
    stt_engine_row.addWidget(stt_fallback_combo, 1)
    settings_layout.addLayout(stt_engine_row)

    def set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    set_combo_data(stt_primary_combo, active_stt["primary"])
    set_combo_data(stt_fallback_combo, active_stt["fallback"])

    vosk_model_row = QHBoxLayout()
    vosk_model_edit = QLineEdit(active_stt["vosk_model_path"])
    vosk_model_edit.setPlaceholderText("Папка распакованной русской модели Vosk")
    choose_vosk_model_button = QPushButton("Папка…")
    download_vosk_model_button = QPushButton("Скачать Vosk RU")
    vosk_model_row.addWidget(QLabel("Модель Vosk"))
    vosk_model_row.addWidget(vosk_model_edit, 1)
    vosk_model_row.addWidget(choose_vosk_model_button)
    vosk_model_row.addWidget(download_vosk_model_button)
    settings_layout.addLayout(vosk_model_row)

    whisper_executable_row = QHBoxLayout()
    whisper_executable_edit = QLineEdit(active_stt["whisper_cpp_executable"])
    whisper_executable_edit.setPlaceholderText("Путь к whisper-cli.exe")
    choose_whisper_executable_button = QPushButton("Выбрать EXE…")
    whisper_executable_row.addWidget(QLabel("Whisper CLI"))
    whisper_executable_row.addWidget(whisper_executable_edit, 1)
    whisper_executable_row.addWidget(choose_whisper_executable_button)
    settings_layout.addLayout(whisper_executable_row)

    whisper_model_row = QHBoxLayout()
    whisper_model_edit = QLineEdit(active_stt["whisper_cpp_model"])
    whisper_model_edit.setPlaceholderText("Путь к GGML-модели .bin")
    choose_whisper_model_button = QPushButton("Выбрать модель…")
    whisper_model_row.addWidget(QLabel("Whisper модель"))
    whisper_model_row.addWidget(whisper_model_edit, 1)
    whisper_model_row.addWidget(choose_whisper_model_button)
    settings_layout.addLayout(whisper_model_row)

    recording_row = QHBoxLayout()
    recording_row.addWidget(QLabel("Длительность записи"))
    recording_duration_combo = QComboBox()
    for seconds in (3, 5, 7, 10, 15):
        recording_duration_combo.addItem(f"{seconds} сек.", float(seconds))
    duration_index = recording_duration_combo.findData(float(active_stt["recording_seconds"]))
    if duration_index >= 0:
        recording_duration_combo.setCurrentIndex(duration_index)
    recording_row.addWidget(recording_duration_combo)
    save_stt_button = QPushButton("Сохранить голосовые настройки")
    recording_row.addWidget(save_stt_button)
    settings_layout.addLayout(recording_row)

    microphone_row = QHBoxLayout()
    microphone_row.addWidget(QLabel("Микрофон"))
    microphone_combo = QComboBox()
    microphone_combo.setMinimumWidth(250)
    refresh_microphones_button = QPushButton("Обновить")
    microphone_row.addWidget(microphone_combo, 1)
    microphone_row.addWidget(refresh_microphones_button)
    settings_layout.addLayout(microphone_row)
    microphone_status = QLabel("Входное устройство по умолчанию.")
    microphone_status.setWordWrap(True)
    microphone_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(microphone_status)

    stt_status = QLabel(
        "Распознавание работает локально. Whisper.cpp активируется только при выборе и указании обоих файлов."
    )
    stt_status.setWordWrap(True)
    stt_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(stt_status)

    always_listen_check = QCheckBox(
        "Hands-free: слушать имя помощника в фоне (локально через Vosk)"
    )
    always_listen_check.setChecked(bool(profile_data.get("always_listen", False)))
    settings_layout.addWidget(always_listen_check)
    wake_listener_status = QLabel("Фоновое прослушивание выключено.")
    wake_listener_status.setWordWrap(True)
    wake_listener_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(wake_listener_status)
    speech_health_button = QPushButton("Проверить голосовую систему")
    settings_layout.addWidget(speech_health_button)
    speech_health_status = QLabel("Диагностика ещё не запускалась.")
    speech_health_status.setWordWrap(True)
    speech_health_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(speech_health_status)

    def refresh_microphone_devices() -> None:
        saved_name = active_microphone["name"]
        microphone_combo.clear()
        microphone_combo.addItem("Системный микрофон по умолчанию", "")
        try:
            from hellsaiz_pc_ai.speech.capture import list_input_devices

            devices = list_input_devices()
            for device in devices:
                microphone_combo.addItem(
                    f"{device.display_name} · {device.max_input_channels} вход.",
                    device.display_name,
                )
            saved_index = microphone_combo.findData(saved_name)
            if saved_name and saved_index < 0:
                active_microphone["name"] = ""
                microphone_status.setText(
                    f"Сохранённый микрофон «{saved_name}» не найден. "
                    "Временно выбрано системное устройство по умолчанию."
                )
                microphone_combo.setCurrentIndex(0)
            else:
                microphone_combo.setCurrentIndex(max(0, saved_index))
                microphone_status.setText(
                    f"Найдено входных устройств: {len(devices)}. "
                    "Выбор действует для push-to-talk и Hands-free."
                )
        except Exception as exc:
            microphone_status.setText(
                f"Не удалось получить список микрофонов: {exc}. "
                "Можно использовать системное устройство по умолчанию."
            )
            microphone_combo.setCurrentIndex(0)

    def choose_vosk_model() -> None:
        selected = QFileDialog.getExistingDirectory(
            window, "Выбрать папку модели Vosk", vosk_model_edit.text()
        )
        if selected:
            vosk_model_edit.setText(selected)

    def download_vosk_model() -> None:
        if any(worker.isRunning() for worker in vosk_model_download_workers):
            stt_status.setText("Загрузка русской модели Vosk уже выполняется.")
            return
        download_vosk_model_button.setEnabled(False)
        stt_status.setText(
            "Загружаю официальную русскую модель Vosk small (около 45 МБ)…"
        )
        worker = VoskModelDownloadWorker(settings.speech.vosk_model_path.parent)
        vosk_model_download_workers.append(worker)

        def model_downloaded(model_path: str) -> None:
            vosk_model_edit.setText(model_path)
            stt_status.setText(
                "Русская модель Vosk установлена локально. Проверяю настройки распознавания…"
            )
            save_stt_profile()

        def model_download_failed(message: str) -> None:
            stt_status.setText(f"Не удалось установить модель Vosk: {message}")

        worker.completed.connect(model_downloaded)
        worker.failed.connect(model_download_failed)
        worker.finished.connect(lambda: download_vosk_model_button.setEnabled(True))
        worker.finished.connect(
            lambda: vosk_model_download_workers.remove(worker)
            if worker in vosk_model_download_workers else None
        )
        worker.start()

    def choose_whisper_executable() -> None:
        selected, _ = QFileDialog.getOpenFileName(
            window, "Выбрать whisper-cli.exe", whisper_executable_edit.text(),
            "Исполняемые файлы (*.exe);;Все файлы (*)",
        )
        if selected:
            whisper_executable_edit.setText(selected)

    def choose_whisper_model() -> None:
        selected, _ = QFileDialog.getOpenFileName(
            window, "Выбрать GGML-модель Whisper.cpp", whisper_model_edit.text(),
            "Модели GGML (*.bin);;Все файлы (*)",
        )
        if selected:
            whisper_model_edit.setText(selected)

    def save_stt_profile() -> None:
        stop_wake_listener()
        primary = str(stt_primary_combo.currentData())
        fallback = str(stt_fallback_combo.currentData())
        if primary == fallback:
            stt_status.setText("Основной и резервный движки должны различаться.")
            return
        if primary == "whisper.cpp" and (
            not whisper_executable_edit.text().strip()
            or not whisper_model_edit.text().strip()
        ):
            stt_status.setText("Для Whisper.cpp укажи и whisper-cli.exe, и GGML-модель.")
            return
        active_microphone["name"] = str(microphone_combo.currentData() or "")
        active_stt.update({
            "primary": primary,
            "fallback": fallback,
            "recording_seconds": float(recording_duration_combo.currentData()),
            "vosk_model_path": vosk_model_edit.text().strip(),
            "whisper_cpp_executable": whisper_executable_edit.text().strip(),
            "whisper_cpp_model": whisper_model_edit.text().strip(),
        })
        profile_data.update({
            "stt_primary": primary,
            "stt_fallback": fallback,
            "vosk_model_path": active_stt["vosk_model_path"],
            "whisper_cpp_executable": active_stt["whisper_cpp_executable"],
            "whisper_cpp_model": active_stt["whisper_cpp_model"],
            "recording_seconds": float(recording_duration_combo.currentData()),
            "always_listen": always_listen_check.isChecked(),
            "microphone_device": active_microphone["name"],
        })
        profile_path = settings.workflows_path.parent / "ai_profile.json"
        try:
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = profile_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(profile_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(profile_path)
            stt_status.setText(
                f"Настройки распознавания сохранены. Основной движок: {primary}; резервный: {fallback}."
            )
            refresh_speech_health()
            if always_listen_check.isChecked():
                start_wake_listener()
            else:
                wake_listener_status.setText("Фоновое прослушивание выключено.")
        except OSError as exc:
            stt_status.setText(f"Не удалось сохранить настройки: {exc}")

    def refresh_speech_health() -> None:
        from hellsaiz_pc_ai.app.health import collect_speech_health

        voice_id = str(profile_data.get("piper_voice_id") or "")
        voice_models = list_installed_voices(settings.workflows_path.parent / "voices")
        selected_model = next(
            (voice for voice in voice_models if voice.voice_id == voice_id), None
        )
        checks = collect_speech_health(
            stt_primary=active_stt["primary"],
            stt_fallback=active_stt["fallback"],
            vosk_model_path=Path(active_stt["vosk_model_path"]),
            whisper_executable=(
                Path(active_stt["whisper_cpp_executable"])
                if active_stt["whisper_cpp_executable"] else None
            ),
            whisper_model=(
                Path(active_stt["whisper_cpp_model"])
                if active_stt["whisper_cpp_model"] else None
            ),
            tts_engine=str(profile_data.get("tts_engine") or "sapi5"),
            piper_model_path=selected_model.model_path if selected_model else None,
            microphone_device=active_microphone["name"],
            wake_enabled=always_listen_check.isChecked(),
        )
        labels = {"ok": "OK", "warning": "WARN", "error": "ERROR"}
        speech_health_status.setText(
            "\\n".join(
                f"[{labels[item.level]}] {item.component}: {item.message}"
                for item in checks
            )
        )

    speech_health_button.clicked.connect(refresh_speech_health)
    refresh_speech_health()

    def stop_wake_listener() -> None:
        worker = wake_listener_state["worker"]
        if worker is None:
            return
        worker.stop_listener()
        if worker.isRunning():
            worker.wait(3000)
        if not worker.isRunning():
            wake_listener_state["worker"] = None

    def start_wake_listener() -> None:
        if not always_listen_check.isChecked():
            return
        if workers:
            QTimer.singleShot(500, start_wake_listener)
            return
        current_worker = wake_listener_state["worker"]
        if current_worker is not None and current_worker.isRunning():
            return
        model_dir = Path(active_stt["vosk_model_path"]).expanduser()
        if not model_dir.is_dir():
            wake_listener_status.setText(
                f"Для активации по имени нужна локальная модель Vosk: {model_dir}"
            )
            always_listen_check.blockSignals(True)
            always_listen_check.setChecked(False)
            always_listen_check.blockSignals(False)
            profile_data["always_listen"] = False
            try:
                profile_path = settings.workflows_path.parent / "ai_profile.json"
                profile_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = profile_path.with_suffix(".json.tmp")
                temporary.write_text(
                    json.dumps(profile_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                temporary.replace(profile_path)
            except OSError as exc:
                logging.warning("Could not persist disabled wake listener: %s", exc)
            return

        worker = WakeListenerWorker(
            model_dir, settings.wake_aliases, active_microphone["name"] or None
        )
        wake_listener_state["worker"] = worker

        def on_wake_command(prompt: str) -> None:
            if not prompt.strip():
                return
            if workers:
                logging.info("Ignoring wake-word command because another action is running.")
                return
            stop_wake_listener()
            start_worker(prompt)

        def on_listener_failed(message: str) -> None:
            wake_listener_status.setText(f"Фоновое прослушивание остановлено: {message}")
            always_listen_check.blockSignals(True)
            always_listen_check.setChecked(False)
            always_listen_check.blockSignals(False)
            profile_data["always_listen"] = False
            try:
                profile_path = settings.workflows_path.parent / "ai_profile.json"
                profile_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = profile_path.with_suffix(".json.tmp")
                temporary.write_text(
                    json.dumps(profile_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                temporary.replace(profile_path)
            except OSError as exc:
                logging.warning("Could not persist wake listener failure: %s", exc)

        dispatcher = WakeListenerDispatcher(
            on_wake_command,
            wake_listener_status.setText,
            on_listener_failed,
        )
        wake_listener_state["dispatcher"] = dispatcher
        worker.dispatcher = dispatcher
        worker.command.connect(dispatcher.dispatch_command)
        worker.status.connect(dispatcher.dispatch_status)
        worker.failed.connect(dispatcher.dispatch_failed)

        def listener_finished() -> None:
            if wake_listener_state["worker"] is worker:
                wake_listener_state["worker"] = None
            if wake_listener_state["dispatcher"] is dispatcher:
                wake_listener_state["dispatcher"] = None

        worker.finished.connect(listener_finished)
        worker.start()

    def resume_wake_listener() -> None:
        if always_listen_check.isChecked():
            QTimer.singleShot(350, start_wake_listener)

    choose_vosk_model_button.clicked.connect(choose_vosk_model)
    download_vosk_model_button.clicked.connect(download_vosk_model)
    choose_whisper_executable_button.clicked.connect(choose_whisper_executable)
    choose_whisper_model_button.clicked.connect(choose_whisper_model)
    save_stt_button.clicked.connect(save_stt_profile)
    refresh_microphones_button.clicked.connect(refresh_microphone_devices)
    always_listen_check.toggled.connect(lambda _checked: save_stt_profile())
    refresh_microphone_devices()

    update_title = QLabel("ОБНОВЛЕНИЯ")
    update_title.setStyleSheet("color:#c8cdd5; font-size:11px; letter-spacing:1.6px;")
    settings_layout.addWidget(update_title)
    update_preferences_path = settings.workflows_path.parent / "updates.json"
    update_preferences: dict[str, Any] = {"auto_check": True}
    if update_preferences_path.is_file():
        try:
            saved_preferences = json.loads(update_preferences_path.read_text(encoding="utf-8"))
            if isinstance(saved_preferences, dict):
                update_preferences.update(saved_preferences)
        except (OSError, ValueError, json.JSONDecodeError):
            logging.warning("Update preferences are invalid; defaulting to automatic checks.")

    update_help = QLabel(
        "Репозиторий обновлений приватный. Один раз добавь Fine-grained GitHub Token "
        "с правом Contents: Read для этого репозитория. Ключ хранится через Windows DPAPI. "
        "Автопроверка только сообщает о новой версии — установка запускается вручную."
    )
    update_help.setWordWrap(True)
    update_help.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(update_help)

    auto_update_check = QCheckBox("Автоматически проверять обновления при запуске")
    auto_update_check.setChecked(bool(update_preferences.get("auto_check", True)))
    settings_layout.addWidget(auto_update_check)

    update_key_row = QHBoxLayout()
    update_key_input = QLineEdit()
    update_key_input.setEchoMode(QLineEdit.EchoMode.Password)
    update_key_input.setPlaceholderText("Fine-grained GitHub Token · Contents: Read")
    save_update_key_button = QPushButton("Сохранить ключ")
    update_key_row.addWidget(update_key_input, 1)
    update_key_row.addWidget(save_update_key_button)
    settings_layout.addLayout(update_key_row)

    update_status = QLabel(f"Текущая версия: {current_app_version}.")
    update_status.setWordWrap(True)
    update_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(update_status)
    update_buttons = QHBoxLayout()
    check_update_button = QPushButton("Проверить обновления")
    install_update_button = QPushButton("Скачать и установить")
    install_update_button.setEnabled(False)
    open_release_button = QPushButton("Открыть релиз")
    open_release_button.setEnabled(False)
    update_buttons.addWidget(check_update_button)
    update_buttons.addWidget(install_update_button)
    update_buttons.addWidget(open_release_button)
    settings_layout.addLayout(update_buttons)
    if install_root is None:
        update_status.setText(
            f"Текущая версия: {current_app_version}. Автообновление недоступно при прямом "
            "запуске EXE. Распакуй portable ZIP и запускай HellsaizLauncher.exe из его корня."
        )
    settings_layout.addStretch(1)
    settings_scroll = QScrollArea()
    settings_scroll.setWidgetResizable(True)
    settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
    settings_scroll.setWidget(settings_page)
    tabs.addTab(settings_scroll, "Настройки")

    update_workers: list[QThread] = []
    latest_release_url = ""
    latest_update_info: UpdateInfo | None = None

    class UpdateWorker(QThread):
        checked = Signal(object)
        downloaded = Signal(object)
        failed = Signal(str)

        def __init__(self, download: bool = False) -> None:
            super().__init__()
            self.download = download

        def run(self) -> None:
            try:
                key_path = settings.workflows_path.parent / "update_key.dpapi"
                access_key = load_secret(key_path)
                if not access_key.strip():
                    raise UpdateCheckError(
                        "Не сохранён GitHub Token. Создай Fine-grained token для "
                        "waslnison22-sudo/Hellsaiz-Pc-AI с правом Contents: Read "
                        "и сохрани его в этом разделе."
                    )
                result = check_latest_release(current_app_version, access_key)
                self.checked.emit(result)
                if self.download and result.update_available:
                    if install_root is None:
                        raise UpdateCheckError("Установочная папка не определена.")
                    prepared = download_update(result, access_key, install_root)
                    self.downloaded.emit(prepared)
            except (UpdateCheckError, SecureStoreError, OSError) as exc:
                self.failed.emit(str(exc))
            except Exception as exc:
                logging.exception("Update operation failed")
                self.failed.emit(f"Ошибка обновления: {exc}")

    def persist_update_preferences() -> None:
        update_preferences["auto_check"] = auto_update_check.isChecked()
        try:
            update_preferences_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = update_preferences_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(update_preferences, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(update_preferences_path)
        except OSError as exc:
            update_status.setText(f"Не удалось сохранить настройки обновлений: {exc}")

    def save_update_access_key() -> None:
        key_path = settings.workflows_path.parent / "update_key.dpapi"
        value = update_key_input.text().strip()
        try:
            save_secret(key_path, value)
            update_key_input.clear()
            if value:
                update_status.setText(
                    "GitHub Token защищён DPAPI и сохранён для текущей учётной записи Windows. "
                    "Теперь нажми «Проверить обновления»."
                )
            else:
                update_status.setText(
                    "GitHub Token удалён. Для приватного канала проверка обновлений будет недоступна."
                )
        except SecureStoreError as exc:
            update_status.setText(str(exc))

    def check_for_updates(silent: bool = False) -> None:
        nonlocal latest_update_info
        if any(worker.isRunning() for worker in update_workers):
            return
        latest_update_info = None
        check_update_button.setEnabled(False)
        install_update_button.setEnabled(False)
        update_status.setText("Проверяю канал обновлений…")
        worker = UpdateWorker()
        update_workers.append(worker)

        def on_checked(info: Any) -> None:
            nonlocal latest_release_url, latest_update_info
            check_update_button.setEnabled(True)
            latest_update_info = info if info.update_available else None
            latest_release_url = info.release_url
            open_release_button.setEnabled(bool(latest_release_url))
            install_update_button.setEnabled(
                bool(info.update_available and install_root is not None and info.package_asset_id)
            )
            if info.update_available and install_root is None:
                update_status.setText(
                    f"Доступна версия {info.latest_version}, но приложение запущено напрямую, "
                    "без Launcher. Для автообновления скачай portable ZIP, распакуй его "
                    "целиком и запускай HellsaizLauncher.exe из корневой папки."
                )
            elif info.update_available:
                package_kind = "дельта-пакет" if info.package_mode == "delta" else "полный пакет"
                update_status.setText(
                    f"Доступна версия {info.latest_version}. Подпись проверена. "
                    f"Подготовлен {package_kind}; можно скачать и установить."
                )
            else:
                update_status.setText(f"Установлена последняя версия: {info.current_version}.")
            if not silent:
                logging.info("Update channel checked: latest=%s", info.latest_version)

        def on_failed(message: str) -> None:
            nonlocal latest_update_info
            latest_update_info = None
            check_update_button.setEnabled(True)
            install_update_button.setEnabled(False)
            if silent:
                update_status.setText(f"Автоматическая проверка не выполнена: {message}")
                logging.info("Automatic update check: %s", message)
            else:
                update_status.setText(f"Ошибка проверки обновлений: {message}")

        worker.checked.connect(on_checked)
        worker.failed.connect(on_failed)
        worker.finished.connect(lambda: update_workers.remove(worker) if worker in update_workers else None)
        worker.start()

    auto_update_check.toggled.connect(lambda _: persist_update_preferences())
    save_update_key_button.clicked.connect(save_update_access_key)
    def install_update() -> None:
        if install_root is None or latest_update_info is None:
            return
        if any(worker.isRunning() for worker in update_workers):
            return
        update_status.setText("Скачиваю и проверяю файлы обновления…")
        worker = UpdateWorker(download=True)
        update_workers.append(worker)

        def on_downloaded(prepared: PreparedUpdate) -> None:
            updater = install_root / "HellsaizUpdater.exe"
            if not updater.is_file():
                update_status.setText("Не найден помощник обновления. Переустанови приложение.")
                return
            import os
            import subprocess
            try:
                subprocess.Popen(
                    [
                        str(updater), "--install",
                        "--install-root", str(install_root),
                        "--archive", str(prepared.archive_path),
                        "--manifest", str(prepared.manifest_path),
                        "--signature", str(prepared.signature_path),
                        "--mode", prepared.mode,
                        "--from-version", prepared.from_version,
                        "--parent-pid", str(os.getpid()),
                    ],
                    cwd=str(install_root),
                    close_fds=True,
                )
            except OSError as exc:
                update_status.setText(f"Не удалось запустить помощник обновления: {exc}")
                return
            update_status.setText("Обновление передано помощнику. Приложение закрывается…")
            app.quit()

        def on_download_failed(message: str) -> None:
            update_status.setText(message)

        worker.downloaded.connect(on_downloaded)
        worker.failed.connect(on_download_failed)
        worker.finished.connect(lambda: update_workers.remove(worker) if worker in update_workers else None)
        worker.start()

    check_update_button.clicked.connect(lambda: check_for_updates(False))
    install_update_button.clicked.connect(install_update)
    open_release_button.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl(latest_release_url)) if latest_release_url else None
    )

    # Convert the working pages into a persistent left navigation.
    page_stack = QStackedWidget()
    navigation = QListWidget()
    navigation.setObjectName("mainNavigation")
    navigation.setFixedWidth(194)
    navigation.setSpacing(5)
    page_titles = []
    while tabs.count():
        page_titles.append(tabs.tabText(0))
        page = tabs.widget(0)
        tabs.removeTab(0)
        page_stack.addWidget(page)
    for title in page_titles:
        navigation.addItem(QListWidgetItem(title))
    navigation.currentRowChanged.connect(page_stack.setCurrentIndex)
    navigation.setCurrentRow(0)

    root = QWidget()
    root.setObjectName("appRoot")
    root_layout = QStackedLayout(root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
    wallpaper_layer = QLabel()
    wallpaper_layer.setObjectName("wallpaperLayer")
    wallpaper_layer.setScaledContents(True)
    wallpaper_layer.setStyleSheet("background:#080b11;")
    shell = QWidget()
    shell.setObjectName("appShell")
    shell_layout = QHBoxLayout(shell)
    shell_layout.setContentsMargins(14, 14, 14, 14)
    shell_layout.setSpacing(12)

    sidebar = QFrame()
    sidebar.setObjectName("sidebar")
    sidebar.setFixedWidth(218)
    sidebar_layout = QVBoxLayout(sidebar)
    sidebar_layout.setContentsMargins(16, 18, 16, 16)
    sidebar_layout.setSpacing(13)
    brand_row = QHBoxLayout()
    brand_mark = QLabel("H")
    brand_mark.setObjectName("brandMark")
    brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
    brand_mark.setFixedSize(42, 42)
    brand_name = QLabel("Hellsaiz PC AI")
    brand_name.setStyleSheet("font-size:15px; font-weight:650; color:#f0f4f9;")
    brand_row.addWidget(brand_mark)
    brand_row.addWidget(brand_name, 1)
    sidebar_layout.addLayout(brand_row)
    sidebar_caption = QLabel("PERSONAL ASSISTANT")
    sidebar_caption.setStyleSheet("font-size:9px; letter-spacing:1.7px; color:#788391;")
    sidebar_layout.addWidget(sidebar_caption)
    sidebar_layout.addWidget(navigation, 1)
    sidebar_divider = QFrame()
    sidebar_divider.setFrameShape(QFrame.Shape.HLine)
    sidebar_divider.setObjectName("softDivider")
    sidebar_layout.addWidget(sidebar_divider)
    sidebar_footer = QLabel(f"Локальный режим\nВерсия {current_app_version}")
    sidebar_footer.setStyleSheet("font-size:11px; color:#9ba5b2;")
    sidebar_layout.addWidget(sidebar_footer)

    content_frame = QFrame()
    content_frame.setObjectName("contentFrame")
    content_layout = QVBoxLayout(content_frame)
    content_layout.setContentsMargins(10, 8, 10, 8)
    content_layout.addWidget(page_stack)
    shell_layout.addWidget(sidebar)
    shell_layout.addWidget(content_frame, 1)
    root_layout.addWidget(wallpaper_layer)
    root_layout.addWidget(shell)
    root_layout.setCurrentIndex(1)
    window.setCentralWidget(root)

    def apply_wallpaper() -> None:
        nonlocal wallpaper_movie
        if wallpaper_movie is not None:
            wallpaper_movie.stop()
            wallpaper_movie.deleteLater()
            wallpaper_movie = None
        wallpaper_layer.setPixmap(QPixmap())
        path = wallpaper_store.active_wallpaper()
        if path is None:
            wallpaper_layer.setStyleSheet("background:#080b11;")
            return
        wallpaper_layer.setStyleSheet("background:#080b11;")
        if path.suffix.casefold() == ".gif":
            movie = QMovie(str(path))
            if movie.isValid():
                wallpaper_movie = movie
                wallpaper_layer.setMovie(movie)
                movie.start()
                return
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            wallpaper_layer.setPixmap(pixmap)
        else:
            wallpaper_layer.setStyleSheet("background:#080b11;")

    apply_wallpaper()
    window.setStyleSheet(
        "QMainWindow, QWidget { background:transparent; color:#e8edf4; font-family:'Segoe UI'; }"
        "QFrame#sidebar { background:rgba(10,14,20,224); border:1px solid rgba(218,230,246,42); border-radius:20px; }"
        "QFrame#contentFrame { background:rgba(7,10,15,190); border:1px solid rgba(218,230,246,35); border-radius:20px; }"
        "QFrame#wallpaperPreview, QFrame#profilePanel { background:rgba(24,30,39,196); border:1px solid rgba(215,228,245,55); border-radius:16px; }"
        "QFrame#softDivider { background:rgba(210,225,245,30); border:0; max-height:1px; }"
        "QLabel#brandMark { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(248,251,255,245),stop:1 rgba(126,139,158,200)); color:#111722; border-radius:12px; font-size:23px; font-weight:800; }"
        "QListWidget#mainNavigation { background:transparent; border:0; padding:0; outline:0; }"
        "QListWidget#mainNavigation::item { color:#aab4c1; padding:12px 12px; border-radius:11px; margin:2px 0; }"
        "QListWidget#mainNavigation::item:hover { background:rgba(218,230,246,24); color:#f4f7fb; }"
        "QListWidget#mainNavigation::item:selected { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(215,228,245,50),stop:1 rgba(145,159,180,28)); color:#f5f8fc; border:1px solid rgba(221,233,250,70); }"
        "QTextEdit,QLineEdit,QPlainTextEdit,QComboBox,QListWidget { background:rgba(15,20,28,224); color:#edf2f8; border:1px solid rgba(204,219,239,48); border-radius:12px; padding:10px; selection-background-color:#465265; }"
        "QTextEdit { background:rgba(9,13,19,155); border:1px solid rgba(211,225,244,25); padding:14px; }"
        "QLineEdit { min-height:24px; }"
        "QPushButton { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(48,57,70,224),stop:1 rgba(27,34,44,238)); color:#e8edf4; border:1px solid rgba(211,225,244,55); border-radius:11px; padding:10px 15px; font-weight:550; }"
        "QPushButton:hover { background:rgba(91,105,126,210); border-color:rgba(233,241,251,120); }"
        "QPushButton:disabled { color:#6f7a89; background:rgba(28,34,43,150); border-color:rgba(155,169,188,25); }"
        "QPushButton#sendButton, QPushButton#primaryButton { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f7f9fc,stop:1 #c8d1de); color:#101721; border:1px solid #ffffff; font-weight:700; }"
        "QPushButton#sendButton:hover, QPushButton#primaryButton:hover { background:#ffffff; }"
        "QPushButton#profileButton, QPushButton#voiceButton { background:rgba(24,30,39,222); color:#d5deea; border:1px solid rgba(213,226,244,54); }"
        "QComboBox::drop-down { border:0; width:24px; }"
        "QListWidget::item { padding:9px 10px; border-radius:9px; }"
        "QListWidget::item:selected { background:rgba(207,222,243,42); color:#ffffff; }"
        "QLabel { color:#d7e0eb; background:transparent; }"
        "QCheckBox { color:#d2dbe7; spacing:8px; }"
        "QCheckBox::indicator { width:16px; height:16px; border:1px solid #8793a3; border-radius:5px; background:rgba(16,21,29,230); }"
        "QCheckBox::indicator:checked { background:#e7edf5; border-color:#e7edf5; }"
        "QSplitter::handle { background:rgba(190,207,229,70); }"
    )

    workers: list[Worker] = []

    def start_worker(
        prompt: str = "",
        voice_input: bool = False,
        workflow_trigger: WorkflowTrigger | None = None,
    ) -> None:
        if workflow_trigger is None and not voice_input and not prompt.strip():
            return
        stop_wake_listener()
        if workflow_trigger is not None:
            trigger_labels = {
                "hotkey": "Горячая клавиша",
                "schedule": "Расписание",
                "startup": "Автозапуск",
            }
            label = trigger_labels.get(workflow_trigger.kind, workflow_trigger.kind)
            trigger_value = workflow_trigger.value or "при запуске"
            transcript.append(
                f"<p><b>{escape(label)}:</b> {escape(trigger_value)}</p>"
            )
        elif prompt:
            transcript.append(f"<p><b>Вы:</b> {escape(prompt)}</p>")
        send_button.setEnabled(False)
        voice_button.setEnabled(False)
        profile_button.setEnabled(False)
        input_box.setEnabled(False)
        worker = Worker(
            prompt,
            voice_input,
            speak_toggle.isChecked(),
            workflow_trigger,
            stt_profile=active_stt,
            microphone_device=active_microphone["name"],
            assistant_profile=profile_data,
            voice_name=active_voice["name"],
        )
        workers.append(worker)

        def show_result(recognized: str, answer: str) -> None:
            if voice_input:
                transcript.append(f"<p><b>Распознано:</b> {escape(recognized)}</p>")
            safe_answer = escape(answer).replace("\n", "<br>")
            transcript.append(f"<p><b>Hellsaiz:</b> {safe_answer}</p>")

        worker.completed.connect(show_result)
        worker.completed.connect(lambda *_: refresh_reminder_list())
        worker.failed.connect(
            lambda message: transcript.append(
                f"<p style='color:#c5c9d0;'><b>Ошибка:</b> {escape(message)}</p>"
            )
        )
        worker.finished.connect(lambda: send_button.setEnabled(True))
        worker.finished.connect(lambda: voice_button.setEnabled(True))
        worker.finished.connect(lambda: profile_button.setEnabled(True))
        worker.finished.connect(lambda: input_box.setEnabled(True))
        worker.finished.connect(lambda: workers.remove(worker) if worker in workers else None)
        worker.finished.connect(lambda: QTimer.singleShot(0, dispatch_pending_automations))
        worker.finished.connect(lambda: QTimer.singleShot(350, resume_wake_listener))
        worker.start()

    def send() -> None:
        prompt = input_box.text().strip()
        input_box.clear()
        start_worker(prompt)

    send_button.clicked.connect(send)
    input_box.returnPressed.connect(send)
    voice_button.clicked.connect(lambda: start_worker(voice_input=True))
    if always_listen_check.isChecked():
        QTimer.singleShot(900, start_wake_listener)

    def dispatch_hotkey(workflow_id: str, combo: str) -> None:
        if workers:
            logging.info("Ignoring hotkey %s for %s because another action is running", combo, workflow_id)
            return
        start_worker(workflow_trigger=WorkflowTrigger("hotkey", combo, workflow_id))

    hotkey_bridge = HotkeyBridge()
    hotkey_dispatcher = HotkeyDispatcher(dispatch_hotkey)
    hotkey_bridge.activated.connect(hotkey_dispatcher.dispatch)

    hotkey_service: GlobalHotkeyService | None = None

    def refresh_hotkey_service() -> None:
        nonlocal hotkey_service
        if hotkey_service is not None:
            hotkey_service.stop()

        hotkey_bindings: dict[str, Any] = {}
        normalized_hotkeys: set[str] = set()
        for workflow_id, graph in workflow_library.list():
            trigger_node = next(
                node for node in graph.nodes if node.kind.startswith("trigger.")
            )
            if trigger_node.kind != "trigger.hotkey":
                continue
            combo = trigger_node.config["hotkey"]
            normalized = combo.casefold()
            if normalized in normalized_hotkeys:
                logging.warning(
                    "Duplicate global hotkey %s in workflow %s; keeping first binding",
                    combo,
                    workflow_id,
                )
                continue
            normalized_hotkeys.add(normalized)
            hotkey_bindings[combo] = (
                lambda workflow_id=workflow_id, combo=combo: hotkey_bridge.activated.emit(
                    workflow_id, combo
                )
            )

        hotkey_service = GlobalHotkeyService(hotkey_bindings)
        try:
            hotkey_service.start()
            if hotkey_bindings:
                scenario_status.setText(
                    f"Глобальные горячие клавиши активны: {', '.join(hotkey_bindings)}"
                )
            else:
                scenario_status.setText("Сохранённых глобальных горячих клавиш нет.")
        except HotkeyUnavailableError as exc:
            scenario_status.setText(str(exc))
            logging.warning("Global hotkeys unavailable: %s", exc)
        except Exception:
            logging.exception("Global hotkey service failed to start")
            scenario_status.setText("Не удалось включить глобальные горячие клавиши.")

    refresh_hotkey_service()

    app.aboutToQuit.connect(
        lambda: hotkey_service.stop() if hotkey_service is not None else None
    )

    def release_speech_runtime() -> None:
        stop_wake_listener()
        try:
            from hellsaiz_pc_ai.speech.vosk import VoskTranscriber

            VoskTranscriber.clear_model_cache()
        except Exception:
            logging.exception("Could not release cached Vosk models during shutdown")
        instance_lock.release()

    app.aboutToQuit.connect(release_speech_runtime)

    scheduler = WorkflowScheduler(
        workflow_library,
        settings.workflows_path.parent / "workflow_schedule_state.json",
    )
    pending_automations: list[WorkflowTrigger] = []

    def dispatch_pending_automations() -> None:
        if workers or not pending_automations:
            return
        next_trigger = pending_automations.pop(0)
        start_worker(workflow_trigger=next_trigger)

    def poll_workflow_automations() -> None:
        try:
            due = scheduler.poll()
            for workflow_id, trigger in due:
                pending_automations.append(trigger)
                logging.info(
                    "Queued workflow trigger %s for scenario %s",
                    trigger.kind,
                    workflow_id,
                )
            dispatch_pending_automations()
        except (OSError, ValueError, json.JSONDecodeError):
            logging.exception("Workflow schedule polling failed")

    workflow_timer = QTimer(window)
    workflow_timer.setInterval(1000)
    workflow_timer.timeout.connect(poll_workflow_automations)

    tray_icon = QSystemTrayIcon(
        app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),
        window,
    )
    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    if tray_available:
        tray_icon.show()

    def poll_due_reminders() -> None:
        try:
            due_reminders = reminder_store.take_due()
            for reminder in due_reminders:
                transcript.append(
                    f"<p><b>Напоминание #{reminder.id}:</b> {escape(reminder.message)}</p>"
                )
                if tray_icon.isVisible():
                    tray_icon.showMessage(
                        "Hellsaiz PC AI",
                        reminder.message,
                        QSystemTrayIcon.MessageIcon.Information,
                        10000,
                    )
                else:
                    QMessageBox.information(
                        window,
                        "Напоминание",
                        reminder.message,
                        QMessageBox.StandardButton.Ok,
                    )
            if due_reminders:
                refresh_reminder_list()
        except (OSError, ValueError):
            logging.exception("Reminder polling failed")

    reminder_timer = QTimer(window)
    reminder_timer.setInterval(1000)
    reminder_timer.timeout.connect(poll_due_reminders)

    # Restore overdue reminders and startup workflows after the main window enters the event loop.
    window.show()
    if install_root is not None:
        try:
            marker = install_root / "health" / f"{current_app_version}.ok"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("ok", encoding="ascii")
        except OSError:
            logging.exception("Could not write update health marker")
    QTimer.singleShot(0, poll_workflow_automations)
    QTimer.singleShot(0, poll_due_reminders)
    if auto_update_check.isChecked():
        QTimer.singleShot(1400, lambda: check_for_updates(True))
    workflow_timer.start()
    reminder_timer.start()
    return app.exec()

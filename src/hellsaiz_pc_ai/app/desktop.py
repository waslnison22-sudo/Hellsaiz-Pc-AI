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
from hellsaiz_pc_ai import startup_task
from hellsaiz_pc_ai.network import v2raytun
from hellsaiz_pc_ai.telegram import (
    TelegramBotWorker,
    TelegramSettings,
    load_settings as load_telegram_settings,
    save_settings as save_telegram_settings,
)
from hellsaiz_pc_ai.version import APP_VERSION
from hellsaiz_pc_ai.core.orchestrator import AssistantOrchestrator
from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.hotkeys import GlobalHotkeyService, HotkeyUnavailableError
from hellsaiz_pc_ai.providers.openai_compatible import OpenAICompatibleProvider, ProviderError
from hellsaiz_pc_ai.providers.gigachat import GigaChatProvider
from hellsaiz_pc_ai.provider_profiles import (
    active_profile as get_active_provider_profile,
    default_profile_store,
    load_profile_store,
    save_profile_store,
    upsert_profile,
    provider_credential_path,
)
from hellsaiz_pc_ai.storage.reminders import ReminderStore
from hellsaiz_pc_ai.storage.sqlite_store import ChatStore
from hellsaiz_pc_ai.tools.clipboard import register_clipboard_tools
from hellsaiz_pc_ai.tools.reminders import register_reminder_tools
from hellsaiz_pc_ai.tools.system import register_system_tools
from hellsaiz_pc_ai.tools.public_info import register_public_info_tools
from hellsaiz_pc_ai.app.wallpaper import WallpaperError, WallpaperStore
from hellsaiz_pc_ai.app.theme import build_dark_stylesheet
from hellsaiz_pc_ai.app.file_access import (
    FileAccessSettings,
    load_file_access_settings,
    save_file_access_settings,
)
from hellsaiz_pc_ai.app.shortcuts import ensure_desktop_shortcut
from hellsaiz_pc_ai.app.single_instance import SingleInstanceLock
from hellsaiz_pc_ai.speech.voice_library import (
    VoiceLibraryError, download_voice, list_installed_voices,
)
from hellsaiz_pc_ai.speech.piper import PiperSynthesizer
from hellsaiz_pc_ai.tools.windows import register_windows_tools
from hellsaiz_pc_ai.tools.window_control import register_window_tools
from hellsaiz_pc_ai.tools.file_system import register_file_system_tools
from hellsaiz_pc_ai.tools.ui_automation import register_ui_automation_tools
from hellsaiz_pc_ai.tools.screen_ocr import (
    clear_ocr_engine_cache,
    register_screen_ocr_tools,
)
from hellsaiz_pc_ai.tools.ocr_models import (
    check_russian_ocr_models,
    download_russian_ocr_models,
)
from hellsaiz_pc_ai.workflows.builder import append_hour_condition, append_repeat_action, append_tool_action, append_wait_action, append_weekday_condition, terminal_nodes
from hellsaiz_pc_ai.workflows.graph import WorkflowGraph, WorkflowGraphRunner, WorkflowTrigger
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary
from hellsaiz_pc_ai.workflows.scheduler import WorkflowScheduler


_BACKGROUND_VOICE_WORKERS: dict[str, list[Any]] = {
    "tests": [],
    "sapi_inventory": [],
}


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
    register_ui_automation_tools(registry)
    register_clipboard_tools(registry)

    file_access_path = settings.workflows_path.parent / "file_access.json"
    try:
        file_access_settings = load_file_access_settings(file_access_path)
    except ValueError as exc:
        logging.warning("File access settings are invalid; using safe default folders: %s", exc)
        from hellsaiz_pc_ai.tools.file_system import default_allowed_roots

        file_access_settings = FileAccessSettings(list(default_allowed_roots()), False)
    register_file_system_tools(
        registry,
        lambda: tuple(file_access_settings.roots),
        allow_writes=lambda: file_access_settings.allow_writes,
    )

    vision_settings_path = settings.workflows_path.parent / "vision.json"
    ocr_models_root = settings.workflows_path.parent / "models" / "ocr_ru"
    vision_settings: dict[str, Any] = {"ocr_enabled": False}
    if vision_settings_path.is_file():
        try:
            saved_vision_settings = json.loads(vision_settings_path.read_text(encoding="utf-8"))
            if (
                isinstance(saved_vision_settings, dict)
                and isinstance(saved_vision_settings.get("ocr_enabled", False), bool)
            ):
                vision_settings["ocr_enabled"] = saved_vision_settings.get("ocr_enabled", False)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            logging.warning("Vision settings are invalid; local OCR will stay disabled.")
    register_screen_ocr_tools(
        registry,
        enabled=lambda: bool(vision_settings["ocr_enabled"]),
        model_root=ocr_models_root,
    )

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

    provider_profiles_path = settings.workflows_path.parent / "provider_profiles.json"
    try:
        provider_profile_store = load_profile_store(
            provider_profiles_path,
            legacy_profile={
                **profile_data,
                "base_url": profile_data.get("base_url") or settings.llm.base_url,
                "model": profile_data.get("model") or settings.llm.model,
                "enabled": profile_data.get("enabled", settings.llm.enabled),
            },
        )
        profile_data.update(get_active_provider_profile(provider_profile_store))
    except ValueError as exc:
        logging.warning("Named AI profiles are invalid; using a clean default: %s", exc)
        provider_profile_store = default_profile_store(
            base_url=settings.llm.base_url,
            model=settings.llm.model,
            enabled=settings.llm.enabled,
        )
        profile_data.update(get_active_provider_profile(provider_profile_store))

    profile_enabled = bool(profile_data.get("enabled", settings.llm.enabled))
    profile_base_url = str(profile_data.get("base_url") or settings.llm.base_url).rstrip("/")
    profile_model = str(profile_data.get("model") or settings.llm.model)
    assistant = None
    if profile_enabled:
        try:
            provider_type = str(profile_data.get("provider") or "lm-studio")
            if provider_type == "gigachat":
                profile_name = str(profile_data.get("name") or "GigaChat")
                credential_path = provider_credential_path(
                    settings.workflows_path.parent, profile_name
                )
                authorization_key = load_secret(credential_path)
                if not authorization_key:
                    logging.warning(
                        "GigaChat profile '%s' is enabled but has no DPAPI-protected authorization key.",
                        profile_name,
                    )
                else:
                    provider = GigaChatProvider(
                        authorization_key,
                        profile_model,
                        base_url=profile_base_url or GigaChatProvider.DEFAULT_BASE_URL,
                        timeout_seconds=settings.llm.timeout_seconds,
                    )
                    assistant = AssistantOrchestrator(
                        provider, registry, settings.llm.system_prompt, settings.llm.max_tool_rounds
                    )
            else:
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
        except (ProviderError, SecureStoreError, ValueError) as exc:
            logging.warning("The active AI profile could not be initialized: %s", exc)

    store = ChatStore(settings.database_path)
    if assistant is not None:
        assistant.history = store.recent_messages()
    workflow_library = WorkflowLibrary(settings.workflows_path)
    workflow_runner = WorkflowGraphRunner(registry)
    return (
        router, assistant, store, workflow_library, workflow_runner,
        registry, reminder_store, allowed_apps, profile_data, file_access_settings,
        vision_settings
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
        from hellsaiz_pc_ai.app.hud import AnimatedPageStack
        from hellsaiz_pc_ai.app.workflow_studio import WorkflowStudioPage
        from hellsaiz_pc_ai.telegram.config import TelegramSettings, load_settings as load_telegram_settings, save_settings as save_telegram_settings
        from hellsaiz_pc_ai.telegram.worker import TelegramBotWorker
        from hellsaiz_pc_ai.app.ui_workers import (
            HotkeyBridge,
            HotkeyDispatcher,
            NetworkProbeWorker,
            OcrModelsWorker,
            ProviderHealthWorker,
            SapiVoiceListWorker,
            StartupTaskWorker,
            SystemHealthBridge,
            SystemHealthWorker,
            TelegramStatusBridge,
            UpdateWorker,
            VoskModelDownloadWorker,
            VoiceDownloadWorker,
            VoiceTestWorker,
            WakeListenerDispatcher,
            WakeListenerWorker,
        )
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
        reminder_store, allowed_apps, profile_data, file_access_settings,
        vision_settings
    ) = build_runtime(settings)
    file_access_path = settings.workflows_path.parent / "file_access.json"
    vision_settings_path = settings.workflows_path.parent / "vision.json"
    active_voice = {"name": str(profile_data.get("voice_name") or settings.speech.tts_voice_name)}
    telegram_config_path = settings.workflows_path.parent / "telegram.json"
    telegram_token_path = settings.workflows_path.parent / "telegram_token.dpapi"
    try:
        telegram_settings = load_telegram_settings(telegram_config_path)
    except (ValueError, SecureStoreError, OSError) as exc:
        logging.warning("Telegram settings or DPAPI token are unavailable; bot will stay disabled: %s", exc)
        telegram_settings = TelegramSettings()

    network_settings_path = settings.workflows_path.parent / "network.json"
    try:
        network_settings = v2raytun.load_network_settings(network_settings_path)
    except ValueError as exc:
        logging.warning("Network settings are invalid; using safe defaults: %s", exc)
        network_settings = {
            "schema_version": 1,
            "executable_path": "",
            "proxy_url": "",
            "health_url": v2raytun.DEFAULT_HEALTH_URL,
            "require_proxy_for_telegram": True,
            "launch_on_start": False,
        }
    raw_tts_rate = profile_data.get("tts_rate", settings.speech.tts_rate)
    tts_rate = (
        int(raw_tts_rate)
        if isinstance(raw_tts_rate, int)
        and not isinstance(raw_tts_rate, bool)
        and 80 <= raw_tts_rate <= 300
        else settings.speech.tts_rate
    )
    raw_tts_volume = profile_data.get("tts_volume", settings.speech.tts_volume)
    tts_volume = (
        float(raw_tts_volume)
        if isinstance(raw_tts_volume, (int, float))
        and not isinstance(raw_tts_volume, bool)
        and 0.0 <= float(raw_tts_volume) <= 1.0
        else settings.speech.tts_volume
    )
    active_tts = {"rate": tts_rate, "volume": tts_volume}
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


    vosk_model_download_workers: list[VoskModelDownloadWorker] = []


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
            tts_profile: dict[str, Any] | None = None,
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
            self.tts_profile = dict(tts_profile or active_tts)

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
                                self.tts_profile["rate"],
                                self.tts_profile["volume"],
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

    provider_profile_store_path = settings.workflows_path.parent / "provider_profiles.json"
    try:
        provider_profile_store = load_profile_store(
            provider_profile_store_path,
            legacy_profile=profile_data,
        )
    except ValueError as exc:
        logging.warning("Could not load named AI profiles: %s", exc)
        provider_profile_store = default_profile_store(
            base_url=settings.llm.base_url,
            model=settings.llm.model,
            enabled=settings.llm.enabled,
        )

    named_profile_row = QHBoxLayout()
    named_profile_label = QLabel("Профиль")
    named_profile_label.setMinimumWidth(95)
    named_profile_combo = QComboBox()
    named_profile_combo.setMinimumWidth(190)
    named_profile_name = QLineEdit()
    named_profile_name.setPlaceholderText("Название профиля")
    named_profile_row.addWidget(named_profile_label)
    named_profile_row.addWidget(named_profile_combo)
    named_profile_row.addWidget(named_profile_name, 1)
    profile_layout.addLayout(named_profile_row)

    provider_row = QHBoxLayout()
    provider_label = QLabel("Провайдер")
    provider_label.setMinimumWidth(95)
    provider_combo = QComboBox()
    provider_combo.addItem("LM Studio", "lm-studio")
    provider_combo.addItem("Ollama", "ollama")
    provider_combo.addItem("llama.cpp", "llama.cpp")
    provider_combo.addItem("GigaChat API", "gigachat")
    provider_combo.addItem("Другой OpenAI-совместимый", "custom")
    provider_combo.setMinimumWidth(180)
    endpoint_edit = QLineEdit()
    endpoint_edit.setPlaceholderText("Адрес локального OpenAI-совместимого сервера")
    endpoint_edit.setMinimumWidth(260)
    provider_row.addWidget(provider_label)
    provider_row.addWidget(provider_combo)
    provider_row.addWidget(endpoint_edit, 1)
    profile_layout.addLayout(provider_row)

    gigachat_key_row = QHBoxLayout()
    gigachat_key_label = QLabel("Ключ GigaChat")
    gigachat_key_label.setMinimumWidth(95)
    gigachat_key_edit = QLineEdit()
    gigachat_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
    gigachat_key_edit.setPlaceholderText("Authorization key из кабинета GigaChat API")
    gigachat_key_status = QLabel("Ключ хранится через Windows DPAPI.")
    gigachat_key_status.setStyleSheet("color:#89919d; font-size:11px;")
    gigachat_key_row.addWidget(gigachat_key_label)
    gigachat_key_row.addWidget(gigachat_key_edit, 1)
    profile_layout.addLayout(gigachat_key_row)

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

    provider_health_row = QHBoxLayout()
    provider_health_button = QPushButton("Проверить соединение и модели")
    model_candidates_combo = QComboBox()
    model_candidates_combo.setMinimumWidth(260)
    model_candidates_combo.addItem("Список моделей не загружен", None)
    provider_health_row.addWidget(provider_health_button)
    provider_health_row.addWidget(model_candidates_combo, 1)
    profile_layout.addLayout(provider_health_row)

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
    profile_apply_button = QPushButton("Применить и сохранить")
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
        "llama.cpp": settings.llm.base_url,
        "gigachat": GigaChatProvider.DEFAULT_BASE_URL,
        "custom": settings.llm.base_url,
    }

    def refresh_named_profile_combo(selected_name: str) -> None:
        named_profile_combo.blockSignals(True)
        named_profile_combo.clear()
        for saved_profile in provider_profile_store["profiles"]:
            named_profile_combo.addItem(saved_profile["name"], saved_profile["name"])
        selected_index = named_profile_combo.findData(selected_name)
        if selected_index >= 0:
            named_profile_combo.setCurrentIndex(selected_index)
        named_profile_combo.blockSignals(False)
        named_profile_name.setText(selected_name)

    def load_named_profile(index: int) -> None:
        profile_name = named_profile_combo.itemData(index)
        if not isinstance(profile_name, str):
            return
        saved_profile = next(
            (item for item in provider_profile_store["profiles"] if item["name"] == profile_name),
            None,
        )
        if saved_profile is None:
            return
        provider_index = provider_combo.findData(saved_profile["provider"])
        if provider_index >= 0:
            provider_combo.setCurrentIndex(provider_index)
        endpoint_edit.setText(saved_profile["base_url"])
        model_edit.setText(saved_profile["model"])
        ai_enabled_check.setChecked(saved_profile["enabled"])
        named_profile_name.setText(saved_profile["name"])
        provider_changed()
        if saved_profile["provider"] == "gigachat":
            stored_key_path = provider_credential_path(
                settings.workflows_path.parent, saved_profile["name"]
            )
            try:
                has_key = bool(load_secret(stored_key_path))
            except SecureStoreError:
                has_key = False
            gigachat_key_status.setText(
                "Ключ сохранён через DPAPI. Введи новый, чтобы заменить."
                if has_key else "Ключ ещё не сохранён. Вставь Authorization key."
            )
        profile_status.setText(f"Выбран профиль «{saved_profile['name']}». Нажми «Применить и сохранить».")

    refresh_named_profile_combo(provider_profile_store["active_profile"])
    named_profile_combo.currentIndexChanged.connect(load_named_profile)

    saved_provider = str(profile_data.get("provider") or "lm-studio")
    provider_index = provider_combo.findData(saved_provider)
    if provider_index >= 0:
        provider_combo.setCurrentIndex(provider_index)
    endpoint_edit.setText(str(profile_data.get("base_url") or settings.llm.base_url))
    model_edit.setText(str(profile_data.get("model") or settings.llm.model))
    ai_enabled_check.setChecked(bool(profile_data.get("enabled", settings.llm.enabled)))
    speak_toggle.setChecked(bool(profile_data.get("auto_speak", settings.speech.auto_speak)))

    provider_selection_state = {
        "last": str(provider_combo.currentData() or "custom")
    }

    def provider_changed() -> None:
        provider = str(provider_combo.currentData() or "custom")
        if provider != provider_selection_state["last"]:
            endpoint_edit.setText(endpoint_defaults.get(provider, settings.llm.base_url))
            provider_selection_state["last"] = provider
        is_gigachat = provider == "gigachat"
        gigachat_key_label.setVisible(is_gigachat)
        gigachat_key_edit.setVisible(is_gigachat)
        gigachat_key_status.setVisible(is_gigachat)
        if is_gigachat and provider != provider_selection_state.get("loaded_provider"):
            endpoint_edit.setText(GigaChatProvider.DEFAULT_BASE_URL)
        provider_selection_state["loaded_provider"] = provider

    provider_combo.currentIndexChanged.connect(provider_changed)
    provider_changed()

    provider_health_workers: list[QThread] = []

    def apply_discovered_model(index: int) -> None:
        value = model_candidates_combo.itemData(index)
        if isinstance(value, str) and value:
            model_edit.setText(value)

    model_candidates_combo.currentIndexChanged.connect(apply_discovered_model)

    def check_provider_connection() -> None:
        if any(worker.isRunning() for worker in provider_health_workers):
            return
        selected_provider = str(provider_combo.currentData() or "custom")
        try:
            if selected_provider == "gigachat":
                profile_name = named_profile_name.text().strip()
                credential_path = provider_credential_path(
                    settings.workflows_path.parent, profile_name
                )
                authorization_key = gigachat_key_edit.text().strip() or load_secret(credential_path)
                if not authorization_key:
                    profile_status.setText("Сначала укажи Authorization key GigaChat API.")
                    return
                provider = GigaChatProvider(
                    authorization_key,
                    model_edit.text().strip() or "GigaChat",
                    base_url=endpoint_edit.text().strip() or GigaChatProvider.DEFAULT_BASE_URL,
                    timeout_seconds=settings.llm.timeout_seconds,
                )
            else:
                provider = OpenAICompatibleProvider(
                    endpoint_edit.text().strip(),
                    model_edit.text().strip() or "local-model",
                    settings.llm.api_key,
                    settings.llm.timeout_seconds,
                    settings.allow_remote_llm,
                )
        except Exception as exc:
            profile_status.setText(f"Проверка не запущена: {exc}")
            return

        provider_health_button.setEnabled(False)
        profile_status.setText("Проверяю соединение и получаю список моделей…")
        worker = ProviderHealthWorker(provider)
        provider_health_workers.append(worker)

        def on_provider_health(result: Any) -> None:
            provider_health_button.setEnabled(True)
            models = result.get("models", []) if isinstance(result, dict) else []
            model_candidates_combo.clear()
            if isinstance(models, list) and models:
                for item in models:
                    if isinstance(item, str):
                        model_candidates_combo.addItem(item, item)
                current_index = model_candidates_combo.findData(model_edit.text().strip())
                if current_index >= 0:
                    model_candidates_combo.setCurrentIndex(current_index)
                model_available = result.get("model_available")
                model_label = "найдена" if model_available else "не найдена в списке"
                profile_status.setText(
                    f"Соединение установлено · {len(models)} моделей · "
                    f"модель «{result.get('model', '')}» {model_label}."
                )
            else:
                model_candidates_combo.addItem("Сервер не вернул список моделей", None)
                profile_status.setText("Соединение установлено, но список моделей пуст.")
        def on_provider_health_failed(message: str) -> None:
            provider_health_button.setEnabled(True)
            profile_status.setText(f"Проверка провайдера не прошла: {message}")
        worker.completed.connect(on_provider_health)
        worker.failed.connect(on_provider_health_failed)
        worker.finished.connect(
            lambda: provider_health_workers.remove(worker)
            if worker in provider_health_workers else None
        )
        worker.start()

    provider_health_button.clicked.connect(check_provider_connection)

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
        nonlocal assistant, provider_profile_store
        endpoint = endpoint_edit.text().strip().rstrip("/")
        model = model_edit.text().strip()
        enabled = ai_enabled_check.isChecked()
        profile_name = named_profile_name.text().strip()
        if not profile_name:
            profile_status.setText("Укажи название AI-профиля.")
            return
        if enabled and (not endpoint.startswith(("http://", "https://")) or not model):
            profile_status.setText("Укажи корректный адрес сервера и имя модели.")
            return

        selected_provider = str(provider_combo.currentData() or "custom")
        new_assistant = None
        pending_gigachat_key = ""
        if enabled:
            try:
                if selected_provider == "gigachat":
                    credential_path = provider_credential_path(
                        settings.workflows_path.parent, profile_name
                    )
                    pending_gigachat_key = gigachat_key_edit.text().strip()
                    authorization_key = pending_gigachat_key or load_secret(credential_path)
                    if not authorization_key:
                        profile_status.setText(
                            "Для GigaChat нужен Authorization key. Ключ будет защищён DPAPI."
                        )
                        return
                    provider = GigaChatProvider(
                        authorization_key,
                        model,
                        base_url=endpoint or GigaChatProvider.DEFAULT_BASE_URL,
                        timeout_seconds=settings.llm.timeout_seconds,
                    )
                else:
                    provider = OpenAICompatibleProvider(
                        endpoint,
                        model,
                        settings.llm.api_key,
                        settings.llm.timeout_seconds,
                        settings.allow_remote_llm,
                    )
                new_assistant = AssistantOrchestrator(
                    provider, registry, settings.llm.system_prompt, settings.llm.max_tool_rounds
                )
                new_assistant.history = store.recent_messages()
            except Exception as exc:
                profile_status.setText(f"Не удалось применить ИИ-профиль: {exc}")
                return

        provider_profile = {
            "name": profile_name,
            "provider": selected_provider,
            "base_url": endpoint or settings.llm.base_url,
            "model": model or settings.llm.model,
            "enabled": enabled,
        }
        try:
            updated_store = upsert_profile(provider_profile_store, provider_profile, activate=True)
            save_profile_store(provider_profile_store_path, updated_store)
        except (OSError, ValueError) as exc:
            profile_status.setText(f"Не удалось сохранить AI-профиль: {exc}")
            return
        provider_profile_store = updated_store
        refresh_named_profile_combo(profile_name)
        if selected_provider == "gigachat":
            try:
                if pending_gigachat_key:
                    save_secret(
                        provider_credential_path(settings.workflows_path.parent, profile_name),
                        pending_gigachat_key,
                    )
                    gigachat_key_edit.clear()
                gigachat_key_status.setText("Ключ защищён DPAPI для текущей учётной записи Windows.")
            except SecureStoreError as exc:
                profile_status.setText(f"AI-профиль сохранён, но ключ не сохранён: {exc}")
                return

        assistant = new_assistant
        selected_voice = voice_combo.currentText()
        if selected_voice:
            active_voice["name"] = selected_voice
        profile_data.update({
            **provider_profile,
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
            profile_status.setText(f"Профиль «{profile_name}» сохранён. Настройки применены.")
        except OSError as exc:
            profile_status.setText(f"AI-профиль сохранён, но голосовые настройки не сохранены: {exc}")

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

    # Guided scenario studio: everyday users never edit graph JSON or node IDs.
    scenario_page = WorkflowStudioPage(
        workflow_library,
        registry,
        allowed_apps=allowed_apps,
        allowed_processes=settings.allowed_processes,
    )
    scenario_status = scenario_page.status_label
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
    test_system_voice_button = QPushButton("Проверить голос Windows")
    voice_actions.addWidget(use_voice_button)
    voice_actions.addWidget(test_piper_voice_button)
    voice_actions.addWidget(use_system_voice_button)
    voice_actions.addWidget(test_system_voice_button)
    voices_layout.addLayout(voice_actions)

    system_voice_row = QHBoxLayout()
    system_voice_row.addWidget(QLabel("Системный голос Windows"))
    system_voice_combo = QComboBox()
    system_voice_combo.setMinimumWidth(240)
    system_voice_combo.addItem("Системный голос по умолчанию", "")
    refresh_system_voices_button = QPushButton("Обновить список")
    system_voice_row.addWidget(system_voice_combo, 1)
    system_voice_row.addWidget(refresh_system_voices_button)
    voices_layout.addLayout(system_voice_row)

    sapi_options_row = QHBoxLayout()
    sapi_options_row.addWidget(QLabel("Скорость SAPI5"))
    sapi_rate_combo = QComboBox()
    for rate in (100, 120, 140, 160, 175, 190, 210, 230, 250, 280):
        sapi_rate_combo.addItem(f"{rate}", rate)
    rate_index = sapi_rate_combo.findData(active_tts["rate"])
    if rate_index >= 0:
        sapi_rate_combo.setCurrentIndex(rate_index)
    sapi_options_row.addWidget(sapi_rate_combo)
    sapi_options_row.addWidget(QLabel("Громкость"))
    sapi_volume_combo = QComboBox()
    for volume in (40, 50, 60, 70, 80, 90, 100):
        sapi_volume_combo.addItem(f"{volume}%", volume)
    volume_index = sapi_volume_combo.findData(round(active_tts["volume"] * 100))
    if volume_index >= 0:
        sapi_volume_combo.setCurrentIndex(volume_index)
    sapi_options_row.addWidget(sapi_volume_combo)
    save_sapi_options_button = QPushButton("Сохранить параметры SAPI5")
    sapi_options_row.addWidget(save_sapi_options_button)
    voices_layout.addLayout(sapi_options_row)
    voices_status = QLabel(
        "Голоса ещё не загружены. Русские модели medium обычно занимают около 60–70 МБ."
    )
    voices_status.setWordWrap(True)
    voices_status.setStyleSheet("color:#9ca7b5;")
    voices_layout.addWidget(voices_status)

    voice_download_workers: list[QThread] = []


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
        worker = VoiceDownloadWorker(voice_id, voice_library_dir)
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

    def persist_voice_profile() -> None:
        profile_path = settings.workflows_path.parent / "ai_profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = profile_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(profile_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(profile_path)

    def save_voice_profile(engine: str, voice_id: str | None = None) -> None:
        profile_data["tts_engine"] = engine
        profile_data["voice_name"] = active_voice["name"]
        profile_data["tts_rate"] = active_tts["rate"]
        profile_data["tts_volume"] = active_tts["volume"]
        if voice_id:
            profile_data["piper_voice_id"] = voice_id
        persist_voice_profile()

    def save_sapi_options() -> None:
        active_tts["rate"] = int(sapi_rate_combo.currentData())
        active_tts["volume"] = float(sapi_volume_combo.currentData()) / 100.0
        profile_data["tts_rate"] = active_tts["rate"]
        profile_data["tts_volume"] = active_tts["volume"]
        try:
            persist_voice_profile()
            voices_status.setText(
                f"Параметры SAPI5 сохранены: {active_tts['rate']} слов/мин, "
                f"{round(active_tts['volume'] * 100)}% громкости."
            )
        except OSError as exc:
            voices_status.setText(f"Не удалось сохранить параметры речи: {exc}")

    def refresh_system_voice_list() -> None:
        if any(worker.isRunning() for worker in _BACKGROUND_VOICE_WORKERS["sapi_inventory"]):
            voices_status.setText("Список системных голосов уже обновляется.")
            return
        refresh_system_voices_button.setEnabled(False)
        voices_status.setText("Получаю список установленных голосов Windows SAPI5…")
        worker = SapiVoiceListWorker(active_tts["rate"], active_tts["volume"])
        _BACKGROUND_VOICE_WORKERS["sapi_inventory"].append(worker)

        def loaded(voices: Any) -> None:
            system_voice_combo.clear()
            system_voice_combo.addItem("Системный голос по умолчанию", "")
            selected_index = 0
            saved_voice = active_voice["name"].casefold().strip()
            for voice in voices:
                system_voice_combo.addItem(voice.name, voice.id)
                if voice.id.casefold() == saved_voice or voice.name.casefold() == saved_voice:
                    selected_index = system_voice_combo.count() - 1
            system_voice_combo.setCurrentIndex(selected_index)
            voices_status.setText(
                f"Найдено системных голосов SAPI5: {len(voices)}. "
                "Выбери голос и нажми «Использовать голос Windows»."
            )
            if saved_voice and selected_index == 0:
                voices_status.setText(
                    f"Сохранённый голос «{active_voice['name']}» не найден среди "
                    f"установленных. Найдено голосов: {len(voices)}."
                )

        def failed(message: str) -> None:
            voices_status.setText(f"Не удалось получить системные голоса: {message}")

        worker.completed.connect(loaded)
        worker.failed.connect(failed)
        worker.finished.connect(lambda: refresh_system_voices_button.setEnabled(True))
        worker.finished.connect(
            lambda: _BACKGROUND_VOICE_WORKERS["sapi_inventory"].remove(worker)
            if worker in _BACKGROUND_VOICE_WORKERS["sapi_inventory"] else None
        )
        worker.start()

    def start_voice_test(engine: str) -> None:
        if workers:
            voices_status.setText("Дождись завершения текущей команды помощника.")
            return
        if any(worker.isRunning() for worker in _BACKGROUND_VOICE_WORKERS["tests"]):
            voices_status.setText("Проверка голосового движка уже выполняется.")
            return
        model_path = None
        voice_name = active_voice["name"]
        if engine == "piper":
            item = installed_voices_list.currentItem()
            if item is None:
                voices_status.setText("Сначала выбери установленную модель Piper.")
                return
            voice_id = str(item.data(Qt.ItemDataRole.UserRole))
            model_path = voice_library_dir / f"{voice_id}.onnx"
        elif engine == "sapi5":
            voice_name = str(system_voice_combo.currentData() or "")
        worker = VoiceTestWorker(
            engine,
            voice_name,
            model_path,
            active_tts["rate"],
            active_tts["volume"],
        )
        _BACKGROUND_VOICE_WORKERS["tests"].append(worker)
        test_piper_voice_button.setEnabled(False)
        test_system_voice_button.setEnabled(False)
        voices_status.setText(f"Проверяю голосовой движок {engine}…")
        worker.completed.connect(voices_status.setText)
        worker.failed.connect(
            lambda message: voices_status.setText(
                f"Не удалось проверить {engine}: {message}"
            )
        )

        def test_finished() -> None:
            test_piper_voice_button.setEnabled(True)
            test_system_voice_button.setEnabled(True)
            if worker in _BACKGROUND_VOICE_WORKERS["tests"]:
                _BACKGROUND_VOICE_WORKERS["tests"].remove(worker)

        worker.finished.connect(test_finished)
        worker.start()

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
        start_voice_test("piper")

    def test_selected_system_voice() -> None:
        start_voice_test("sapi5")

    def use_windows_voice() -> None:
        active_voice["name"] = str(system_voice_combo.currentData() or "")
        try:
            save_voice_profile("sapi5")
            selected_name = system_voice_combo.currentText()
            voices_status.setText(
                f"Для ответов помощника выбран системный голос: {selected_name}."
            )
        except OSError as exc:
            voices_status.setText(f"Не удалось сохранить настройку: {exc}")

    download_voice_button.clicked.connect(download_selected_voice)
    use_voice_button.clicked.connect(use_selected_piper_voice)
    test_piper_voice_button.clicked.connect(test_selected_piper_voice)
    test_system_voice_button.clicked.connect(test_selected_system_voice)
    use_system_voice_button.clicked.connect(use_windows_voice)
    refresh_system_voices_button.clicked.connect(refresh_system_voice_list)
    save_sapi_options_button.clicked.connect(save_sapi_options)
    refresh_voice_library()
    tabs.addTab(voices_page, "Голоса")
    refresh_system_voice_list()

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
    speech_health_button = QPushButton("Проверить состояние приложения")
    speech_health_button.setAccessibleDescription(
        "Запускает фоновую проверку голоса, локальной истории, сценариев и пользовательского хранилища."
    )
    settings_layout.addWidget(speech_health_button)
    health_summary_status = QLabel("Диагностика ещё не запускалась.")
    health_summary_status.setAccessibleName("Итог диагностики")
    health_summary_status.setStyleSheet("font-weight:650; color:#d7e0eb;")
    settings_layout.addWidget(health_summary_status)
    speech_health_status = QLabel(
        "Проверяются голосовые компоненты, SQLite, сценарии и пользовательское хранилище."
    )
    speech_health_status.setWordWrap(True)
    speech_health_status.setAccessibleName("Подробности диагностики")
    speech_health_status.setAccessibleDescription(
        "Проверки состояния голоса, базы данных, сценариев и доступности диска. Текст можно выделить и скопировать."
    )
    speech_health_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    speech_health_status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    speech_health_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(speech_health_status)
    system_health_workers: list[QThread] = []

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
            refresh_system_health()
            if always_listen_check.isChecked():
                start_wake_listener()
            else:
                wake_listener_status.setText("Фоновое прослушивание выключено.")
        except OSError as exc:
            stt_status.setText(f"Не удалось сохранить настройки: {exc}")

    def show_system_health(checks: list[Any]) -> None:
        from hellsaiz_pc_ai.app.health import summarize_health
        level, summary = summarize_health(checks)
        labels = {"ok": "ВСЁ В ПОРЯДКЕ", "warning": "ЕСТЬ ПРЕДУПРЕЖДЕНИЯ", "error": "ОБНАРУЖЕНЫ ОШИБКИ"}
        health_summary_status.setText(f"{labels[level]} · {summary}")
        detail_labels = {"ok": "OK", "warning": "WARN", "error": "ERROR"}
        speech_health_status.setText(
            "\n".join(
                f"[{detail_labels[item.level]}] {item.component}: {item.message}"
                for item in checks
            )
        )

    def refresh_system_health() -> None:
        if any(worker.isRunning() for worker in system_health_workers):
            return
        speech_health_button.setEnabled(False)
        health_summary_status.setText("ВЫПОЛНЯЕТСЯ ДИАГНОСТИКА…")
        speech_health_status.setText("Проверка не открывает микрофон и не изменяет историю или сценарии.")
        worker = SystemHealthWorker(
            active_stt.copy(),
            active_microphone["name"],
            always_listen_check.isChecked(),
            str(profile_data.get("piper_voice_id") or ""),
            str(profile_data.get("tts_engine") or "sapi5"),
            voices_dir=settings.workflows_path.parent / "voices",
            database_path=settings.database_path,
            workflows_path=settings.workflows_path,
        )
        system_health_workers.append(worker)
        worker.completed.connect(system_health_bridge.completed)
        worker.failed.connect(system_health_bridge.failed)
        worker.finished.connect(system_health_bridge.finished)
        worker.start()

    system_health_bridge = SystemHealthBridge(
        summary_status=health_summary_status,
        detail_status=speech_health_status,
        health_button=speech_health_button,
        workers_list=system_health_workers,
        on_completed=show_system_health,
        parent=window,
    )

    speech_health_button.clicked.connect(refresh_system_health)
    refresh_system_health()

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

    ocr_models_root = settings.workflows_path.parent / "models" / "ocr_ru"
    vision_settings_path = settings.workflows_path.parent / "vision.json"
    ocr_model_workers: list[QThread] = []
    ocr_model_state = {"ready": False}

    ocr_title = QLabel("ЛОКАЛЬНОЕ РАСПОЗНАВАНИЕ ЭКРАНА")
    ocr_title.setStyleSheet("color:#c8cdd5; font-size:11px; letter-spacing:1.6px;")
    settings_layout.addWidget(ocr_title)
    ocr_help = QLabel(
        "OCR работает локально на основном мониторе. Снимок не сохраняется и не отправляется "
        "в сеть. Русские ONNX-модели загружаются только после нажатия кнопки."
    )
    ocr_help.setWordWrap(True)
    ocr_help.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(ocr_help)

    ocr_enabled_check = QCheckBox("Разрешить команду «прочитай текст на экране»")
    ocr_enabled_check.setChecked(bool(vision_settings.get("ocr_enabled", False)))
    ocr_enabled_check.setEnabled(False)
    settings_layout.addWidget(ocr_enabled_check)

    ocr_buttons = QHBoxLayout()
    check_ocr_models_button = QPushButton("Проверить модели")
    download_ocr_models_button = QPushButton("Загрузить русские OCR-модели")
    ocr_buttons.addWidget(check_ocr_models_button)
    ocr_buttons.addWidget(download_ocr_models_button)
    settings_layout.addLayout(ocr_buttons)

    ocr_status = QLabel("Проверяю наличие локальных моделей OCR…")
    ocr_status.setWordWrap(True)
    ocr_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(ocr_status)

    def persist_vision_settings() -> bool:
        temporary = vision_settings_path.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                json.dumps(
                    {"schema_version": 1, "ocr_enabled": bool(vision_settings["ocr_enabled"])},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary.replace(vision_settings_path)
            return True
        except (OSError, ValueError) as exc:
            ocr_status.setText(f"Не удалось сохранить разрешение OCR: {exc}")
            return False

    def apply_ocr_model_status(status: Any) -> None:
        ready = bool(getattr(status, "ready", False))
        ocr_model_state["ready"] = ready
        missing = list(getattr(status, "missing", ()))
        invalid = list(getattr(status, "invalid", ()))
        if ready:
            ocr_status.setText("Все три русские OCR-модели установлены и прошли SHA-256 проверку.")
            ocr_enabled_check.setEnabled(True)
        else:
            details = []
            if missing:
                details.append("отсутствуют: " + ", ".join(missing))
            if invalid:
                details.append("повреждены: " + ", ".join(invalid))
            ocr_status.setText(
                "Модели OCR ещё не готовы (" + "; ".join(details) + "). Нажми «Загрузить русские OCR-модели»."
            )
            ocr_enabled_check.blockSignals(True)
            ocr_enabled_check.setChecked(False)
            ocr_enabled_check.blockSignals(False)
            ocr_enabled_check.setEnabled(False)
            if vision_settings.get("ocr_enabled"):
                vision_settings["ocr_enabled"] = False
                persist_vision_settings()
        clear_ocr_engine_cache()

    def on_ocr_worker_progress(key: str, state: str) -> None:
        state_label = "проверена" if state == "already-installed" else "загружена"
        ocr_status.setText(f"OCR-модель {key}: {state_label}…")

    def start_ocr_models_worker(*, download: bool) -> None:
        if any(worker.isRunning() for worker in ocr_model_workers):
            return
        check_ocr_models_button.setEnabled(False)
        download_ocr_models_button.setEnabled(False)
        ocr_status.setText(
            "Загружаю и проверяю русские OCR-модели…"
            if download else "Проверяю SHA-256 русских OCR-моделей…"
        )
        worker = OcrModelsWorker(download=download, models_root=ocr_models_root)
        ocr_model_workers.append(worker)

        def on_completed(status: Any) -> None:
            apply_ocr_model_status(status)

        def on_failed(message: str) -> None:
            ocr_status.setText("OCR не готов: " + message)
            try:
                apply_ocr_model_status(check_russian_ocr_models(ocr_models_root))
            except Exception:
                logging.exception("Could not verify OCR model state after failure")

        worker.progress.connect(on_ocr_worker_progress)
        worker.completed.connect(on_completed)
        worker.failed.connect(on_failed)

        def on_finished() -> None:
            check_ocr_models_button.setEnabled(True)
            download_ocr_models_button.setEnabled(True)
            if worker in ocr_model_workers:
                ocr_model_workers.remove(worker)

        worker.finished.connect(on_finished)
        worker.start()

    def toggle_ocr_permission(enabled: bool) -> None:
        if enabled and not ocr_model_state["ready"]:
            ocr_enabled_check.blockSignals(True)
            ocr_enabled_check.setChecked(False)
            ocr_enabled_check.blockSignals(False)
            ocr_status.setText("Сначала установи и проверь все русские OCR-модели.")
            return
        previous = bool(vision_settings["ocr_enabled"])
        vision_settings["ocr_enabled"] = enabled
        if not persist_vision_settings():
            vision_settings["ocr_enabled"] = previous
            ocr_enabled_check.blockSignals(True)
            ocr_enabled_check.setChecked(previous)
            ocr_enabled_check.blockSignals(False)
            return
        if not enabled:
            clear_ocr_engine_cache()
        ocr_status.setText(
            "Локальный OCR разрешён. Команда работает только после прямого запроса."
            if enabled else "Локальный OCR выключен."
        )

    check_ocr_models_button.clicked.connect(lambda: start_ocr_models_worker(download=False))
    download_ocr_models_button.clicked.connect(lambda: start_ocr_models_worker(download=True))
    ocr_enabled_check.toggled.connect(toggle_ocr_permission)
    QTimer.singleShot(0, lambda: start_ocr_models_worker(download=False))

    file_access_title = QLabel("ДОСТУП К ФАЙЛАМ")
    file_access_title.setStyleSheet("color:#c8cdd5; font-size:11px; letter-spacing:1.6px;")
    settings_layout.addWidget(file_access_title)
    file_access_help = QLabel(
        "Помощник работает только внутри этих папок. Поиск, чтение и открытие доступны сразу. "
        "Создание папок и новых текстовых файлов требует отдельного разрешения. "
        "Удаление и перезапись файлов голосовыми командами недоступны."
    )
    file_access_help.setWordWrap(True)
    file_access_help.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(file_access_help)

    file_roots_list = QListWidget()
    file_roots_list.setMaximumHeight(120)
    for root_path in file_access_settings.roots:
        file_roots_list.addItem(str(root_path))
    settings_layout.addWidget(file_roots_list)

    file_root_buttons = QHBoxLayout()
    add_file_root_button = QPushButton("Добавить папку")
    remove_file_root_button = QPushButton("Убрать выбранную")
    file_root_buttons.addWidget(add_file_root_button)
    file_root_buttons.addWidget(remove_file_root_button)
    settings_layout.addLayout(file_root_buttons)

    allow_file_writes_check = QCheckBox("Разрешить создавать новые папки и текстовые файлы")
    allow_file_writes_check.setChecked(file_access_settings.allow_writes)
    settings_layout.addWidget(allow_file_writes_check)
    file_access_status = QLabel("Папки доступа хранятся локально.")
    file_access_status.setWordWrap(True)
    file_access_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(file_access_status)

    def refresh_file_roots_list() -> None:
        file_roots_list.clear()
        for root_path in file_access_settings.roots:
            file_roots_list.addItem(str(root_path))

    def persist_file_access_settings() -> bool:
        try:
            save_file_access_settings(file_access_path, file_access_settings)
            refresh_file_roots_list()
            file_access_status.setText(
                f"Сохранено разрешённых папок: {len(file_access_settings.roots)}. "
                + (
                    "Создание новых объектов разрешено."
                    if file_access_settings.allow_writes
                    else "Запись и создание объектов отключены."
                )
            )
            return True
        except (OSError, ValueError) as exc:
            file_access_status.setText(f"Не удалось сохранить доступ к файлам: {exc}")
            return False

    def add_file_access_root() -> None:
        selected = QFileDialog.getExistingDirectory(
            window,
            "Разрешить доступ к папке",
            str(Path.home()),
        )
        if not selected:
            return
        candidate = Path(selected).resolve()
        if candidate in file_access_settings.roots:
            file_access_status.setText("Эта папка уже разрешена.")
            return
        if len(file_access_settings.roots) >= 12:
            file_access_status.setText("Можно разрешить не более 12 папок.")
            return
        file_access_settings.roots.append(candidate)
        if not persist_file_access_settings():
            file_access_settings.roots.remove(candidate)

    def remove_file_access_root() -> None:
        item = file_roots_list.currentItem()
        if item is None:
            file_access_status.setText("Сначала выбери папку в списке.")
            return
        target = Path(item.text()).resolve()
        previous = list(file_access_settings.roots)
        file_access_settings.roots[:] = [
            root for root in file_access_settings.roots if root.resolve() != target
        ]
        if not persist_file_access_settings():
            file_access_settings.roots[:] = previous
            refresh_file_roots_list()

    def toggle_file_write_permission(enabled: bool) -> None:
        previous = file_access_settings.allow_writes
        file_access_settings.allow_writes = enabled
        if not persist_file_access_settings():
            file_access_settings.allow_writes = previous
            allow_file_writes_check.blockSignals(True)
            allow_file_writes_check.setChecked(previous)
            allow_file_writes_check.blockSignals(False)

    add_file_root_button.clicked.connect(add_file_access_root)
    remove_file_root_button.clicked.connect(remove_file_access_root)
    allow_file_writes_check.toggled.connect(toggle_file_write_permission)

    network_title = QLabel("СЕТЬ И v2RAYTUN")
    network_title.setStyleSheet("color:#c8cdd5; font-size:11px; letter-spacing:1.6px;")
    settings_layout.addWidget(network_title)
    network_help = QLabel(
        "Выбери официальный клиент вручную и укажи локальный HTTP-порт прокси из его настроек. "
        "Программа не меняет системные маршруты, DNS или прокси Windows; подключение к туннелю "
        "выполняется в самом v2RayTun."
    )
    network_help.setWordWrap(True)
    network_help.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(network_help)

    v2raytun_exe_row = QHBoxLayout()
    v2raytun_exe_edit = QLineEdit(str(network_settings.get("executable_path") or ""))
    v2raytun_exe_edit.setPlaceholderText("Путь к v2RayTun.exe")
    choose_v2raytun_button = QPushButton("Выбрать EXE")
    v2raytun_exe_row.addWidget(v2raytun_exe_edit, 1)
    v2raytun_exe_row.addWidget(choose_v2raytun_button)
    settings_layout.addLayout(v2raytun_exe_row)

    network_proxy_row = QHBoxLayout()
    network_proxy_edit = QLineEdit(str(network_settings.get("proxy_url") or ""))
    network_proxy_edit.setPlaceholderText("Локальный HTTP-прокси, например http://127.0.0.1:10809")
    network_proxy_row.addWidget(network_proxy_edit, 1)
    settings_layout.addLayout(network_proxy_row)

    network_health_row = QHBoxLayout()
    network_health_edit = QLineEdit(str(network_settings.get("health_url") or v2raytun.DEFAULT_HEALTH_URL))
    network_health_edit.setPlaceholderText("HTTPS endpoint для проверки")
    network_health_row.addWidget(network_health_edit, 1)
    settings_layout.addLayout(network_health_row)

    require_proxy_check = QCheckBox("Требовать рабочий прокси перед запуском Telegram")
    require_proxy_check.setChecked(bool(network_settings.get("require_proxy_for_telegram", True)))
    launch_v2raytun_check = QCheckBox("Запускать клиент v2RayTun при старте помощника")
    launch_v2raytun_check.setChecked(bool(network_settings.get("launch_on_start", False)))
    settings_layout.addWidget(require_proxy_check)
    settings_layout.addWidget(launch_v2raytun_check)

    network_buttons = QHBoxLayout()
    launch_v2raytun_button = QPushButton("Запустить клиент")
    check_network_button = QPushButton("Проверить прокси")
    save_network_button = QPushButton("Сохранить сеть")
    network_buttons.addWidget(launch_v2raytun_button)
    network_buttons.addWidget(check_network_button)
    network_buttons.addWidget(save_network_button)
    settings_layout.addLayout(network_buttons)

    network_status = QLabel("Прокси ещё не проверен.")
    network_status.setWordWrap(True)
    network_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(network_status)

    def persist_network_settings() -> bool:
        network_settings.update({
            "executable_path": v2raytun_exe_edit.text().strip(),
            "proxy_url": network_proxy_edit.text().strip(),
            "health_url": network_health_edit.text().strip() or v2raytun.DEFAULT_HEALTH_URL,
            "require_proxy_for_telegram": require_proxy_check.isChecked(),
            "launch_on_start": launch_v2raytun_check.isChecked(),
        })
        try:
            v2raytun.save_network_settings(network_settings_path, network_settings)
            network_status.setText("Сетевые настройки сохранены локально.")
            return True
        except (OSError, ValueError) as exc:
            network_status.setText(f"Не удалось сохранить сетевые настройки: {exc}")
            return False

    def choose_v2raytun_executable() -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            window,
            "Выбрать v2RayTun",
            str(Path.home()),
            "Windows executable (*.exe)",
        )
        if selected:
            v2raytun_exe_edit.setText(selected)
            persist_network_settings()

    def launch_v2raytun_client() -> None:
        if not persist_network_settings():
            return
        executable = v2raytun_exe_edit.text().strip()
        if not executable:
            network_status.setText("Сначала выбери v2RayTun.exe.")
            return
        try:
            if v2raytun.detect_v2raytun_running():
                network_status.setText(
                    "v2RayTun уже запущен. Подключи туннель в самом клиенте и проверь прокси."
                )
                return
            v2raytun.launch_v2raytun(executable)
            network_status.setText(
                "Клиент запущен. Подключи туннель в окне v2RayTun, затем нажми «Проверить прокси»."
            )
        except (ValueError, v2raytun.NetworkDependencyError) as exc:
            network_status.setText(f"Не удалось запустить v2RayTun: {exc}")

    network_workers: list[QThread] = []

    def check_v2raytun_health() -> None:
        if not persist_network_settings():
            return
        if any(worker.isRunning() for worker in network_workers):
            return
        check_network_button.setEnabled(False)
        network_status.setText("Проверяю процесс клиента и HTTPS доступ через прокси…")
        worker = NetworkProbeWorker(network_settings)
        network_workers.append(worker)

        def on_network_completed(status: Any) -> None:
            check_network_button.setEnabled(True)
            prefix = "Доступ разрешён." if status.telegram_ready else "Доступ ограничен."
            network_status.setText(prefix + " " + status.detail)

        def on_network_failed(message: str) -> None:
            check_network_button.setEnabled(True)
            network_status.setText("Проверка сети завершилась ошибкой: " + message)

        worker.completed.connect(on_network_completed)
        worker.failed.connect(on_network_failed)
        worker.finished.connect(
            lambda: network_workers.remove(worker) if worker in network_workers else None
        )
        worker.start()

    choose_v2raytun_button.clicked.connect(choose_v2raytun_executable)
    launch_v2raytun_button.clicked.connect(launch_v2raytun_client)
    check_network_button.clicked.connect(check_v2raytun_health)
    save_network_button.clicked.connect(persist_network_settings)
    require_proxy_check.toggled.connect(lambda _checked: persist_network_settings())
    launch_v2raytun_check.toggled.connect(lambda _checked: persist_network_settings())

    telegram_title = QLabel("TELEGRAM WORKER")
    telegram_title.setStyleSheet("color:#c8cdd5; font-size:11px; letter-spacing:1.6px;")
    settings_layout.addWidget(telegram_title)
    telegram_help = QLabel(
        "Отдельный локальный бот без ИИ. Команды доступны только указанным user ID и chat ID. "
        "Токен хранится через Windows DPAPI. Разрешены только чтение времени, системы и "
        "напоминаний; запуск программ и shell-команд запрещён."
    )
    telegram_help.setWordWrap(True)
    telegram_help.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(telegram_help)

    telegram_token_input = QLineEdit()
    telegram_token_input.setEchoMode(QLineEdit.EchoMode.Password)
    telegram_token_input.setPlaceholderText("Токен бота от BotFather")
    save_telegram_token_button = QPushButton("Сохранить токен")
    telegram_token_row = QHBoxLayout()
    telegram_token_row.addWidget(telegram_token_input, 1)
    telegram_token_row.addWidget(save_telegram_token_button)
    settings_layout.addLayout(telegram_token_row)

    telegram_token_status = QLabel(
        "Токен защищён DPAPI и сохранён."
        if bool(telegram_settings.token) else "Токен не сохранён."
    )
    telegram_token_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(telegram_token_status)

    telegram_users_input = QLineEdit(
        ", ".join(str(value) for value in telegram_settings.allowed_user_ids)
    )
    telegram_users_input.setPlaceholderText("Разрешённые Telegram user ID через запятую")
    telegram_chats_input = QLineEdit(
        ", ".join(str(value) for value in telegram_settings.allowed_chat_ids)
    )
    telegram_chats_input.setPlaceholderText("Разрешённые Telegram chat ID через запятую")
    settings_layout.addWidget(telegram_users_input)
    settings_layout.addWidget(telegram_chats_input)

    telegram_permission_checks: dict[str, QCheckBox] = {}
    for tool_name, command_name, description in (
        ("get_local_time", "/time", "Локальные дата и время"),
        ("get_system_info", "/system", "Сведения о системе"),
        ("list_reminders", "/reminders", "Активные напоминания"),
    ):
        check = QCheckBox(f"{command_name} — {description}")
        check.setChecked(tool_name in telegram_settings.allowed_tools)
        telegram_permission_checks[tool_name] = check
        settings_layout.addWidget(check)

    telegram_settings_row = QHBoxLayout()
    save_telegram_settings_button = QPushButton("Сохранить настройки")
    telegram_enable_check = QCheckBox("Включить Telegram worker")
    telegram_enable_check.setChecked(telegram_settings.enabled)
    telegram_settings_row.addWidget(save_telegram_settings_button)
    telegram_settings_row.addWidget(telegram_enable_check)
    settings_layout.addLayout(telegram_settings_row)

    telegram_status = QLabel("Telegram worker выключен.")
    telegram_status.setWordWrap(True)
    telegram_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(telegram_status)

    telegram_status_bridge = TelegramStatusBridge()
    telegram_status_bridge.status.connect(telegram_status.setText)
    telegram_worker_state: dict[str, Any] = {"worker": None}
    telegram_poll_timer = QTimer(window)
    telegram_poll_timer.setInterval(1000)

    def parse_telegram_ids(value: str, label: str) -> list[int]:
        parts = [item.strip() for item in value.split(",") if item.strip()]
        if len(parts) > 100:
            raise ValueError(f"Для поля «{label}» разрешено не более 100 ID.")
        values: list[int] = []
        for item in parts:
            try:
                identifier = int(item)
            except ValueError as exc:
                raise ValueError(f"Поле «{label}» должно содержать числовые ID.") from exc
            if identifier == 0:
                raise ValueError(f"Поле «{label}» не может содержать ID 0.")
            if identifier not in values:
                values.append(identifier)
        return values

    def persist_telegram_settings(*, enabled: bool | None = None) -> bool:
        try:
            telegram_settings.allowed_user_ids[:] = parse_telegram_ids(
                telegram_users_input.text(), "user ID"
            )
            telegram_settings.allowed_chat_ids[:] = parse_telegram_ids(
                telegram_chats_input.text(), "chat ID"
            )
            telegram_settings.allowed_tools[:] = [
                name for name, check in telegram_permission_checks.items()
                if check.isChecked()
            ]
            if enabled is not None:
                telegram_settings.enabled = enabled
            if telegram_settings.enabled and (
                not telegram_settings.allowed_user_ids or not telegram_settings.allowed_chat_ids
            ):
                raise ValueError("Укажи хотя бы один разрешённый user ID и chat ID.")
            save_telegram_settings(telegram_config_path, telegram_settings)
            telegram_status.setText("Настройки Telegram сохранены.")
            return True
        except (OSError, ValueError, SecureStoreError) as exc:
            telegram_status.setText(f"Не удалось сохранить Telegram: {exc}")
            return False

    def reap_telegram_worker() -> None:
        worker = telegram_worker_state["worker"]
        if worker is not None and not worker.is_alive():
            worker.join(timeout=0)
            telegram_worker_state["worker"] = None
            if telegram_settings.enabled:
                telegram_settings.enabled = False
                telegram_enable_check.blockSignals(True)
                telegram_enable_check.setChecked(False)
                telegram_enable_check.blockSignals(False)
                try:
                    save_telegram_settings(telegram_config_path, telegram_settings)
                except (OSError, ValueError, SecureStoreError):
                    logging.exception("Could not persist stopped Telegram worker state.")
                telegram_status.setText(
                    "Telegram worker завершился. Проверь статус сети и токен бота."
                )

    def start_telegram_worker() -> bool:
        existing = telegram_worker_state["worker"]
        if existing is not None and existing.is_alive():
            telegram_status.setText("Telegram worker уже работает.")
            return False
        try:
            token = load_secret(telegram_token_path)
            if not token:
                raise ValueError("Сначала сохрани токен Telegram-бота.")
            if not persist_telegram_settings(enabled=True):
                return False
            if not telegram_settings.allowed_tools:
                raise ValueError("Разреши хотя бы одну безопасную команду Telegram.")
            proxy_url = str(network_settings.get("proxy_url") or "")
            require_proxy = bool(network_settings.get("require_proxy_for_telegram", True))
            if require_proxy and not proxy_url:
                raise ValueError("Настрой локальный HTTP-прокси или отключи требование прокси.")
            worker = TelegramBotWorker(
                token,
                registry,
                allowed_user_ids=set(telegram_settings.allowed_user_ids),
                allowed_chat_ids=set(telegram_settings.allowed_chat_ids),
                allowed_tools=set(telegram_settings.allowed_tools),
                proxy_url=proxy_url,
                require_proxy=require_proxy,
                health_url=str(network_settings.get("health_url") or v2raytun.DEFAULT_HEALTH_URL),
                app_version=current_app_version,
                status_callback=telegram_status_bridge.status.emit,
            )
            telegram_worker_state["worker"] = worker
            worker.start()
            telegram_status.setText("Telegram worker запускается…")
            return True
        except (OSError, ValueError, SecureStoreError) as exc:
            telegram_status.setText(f"Не удалось запустить Telegram worker: {exc}")
            return False

    def stop_telegram_worker() -> None:
        worker = telegram_worker_state["worker"]
        if worker is None:
            telegram_status.setText("Telegram worker уже остановлен.")
            return
        worker.stop()
        telegram_status.setText("Запрос на остановку Telegram worker отправлен.")

    def toggle_telegram_worker(enabled: bool) -> None:
        if enabled:
            if not start_telegram_worker():
                telegram_enable_check.blockSignals(True)
                telegram_enable_check.setChecked(False)
                telegram_enable_check.blockSignals(False)
                telegram_settings.enabled = False
                try:
                    save_telegram_settings(telegram_config_path, telegram_settings)
                except (OSError, ValueError, SecureStoreError):
                    logging.exception("Could not persist disabled Telegram state.")
        else:
            persist_telegram_settings(enabled=False)
            stop_telegram_worker()

    def save_telegram_bot_token() -> None:
        worker = telegram_worker_state["worker"]
        if worker is not None and worker.is_alive():
            telegram_token_status.setText("Сначала останови Telegram worker.")
            return
        value = telegram_token_input.text().strip()
        try:
            if value:
                from hellsaiz_pc_ai.telegram.config import validate_bot_token
                validate_bot_token(value)
            if value:
                save_secret(telegram_token_path, value)
                telegram_settings.token = value
                telegram_token_status.setText("Токен защищён DPAPI и сохранён.")
            else:
                from hellsaiz_pc_ai.telegram.config import delete_saved_token
                delete_saved_token(telegram_config_path)
                telegram_settings.token = ""
                telegram_token_status.setText("Токен удалён.")
            telegram_token_input.clear()
        except (SecureStoreError, ValueError) as exc:
            telegram_token_status.setText(f"Не удалось сохранить токен: {exc}")

    def save_telegram_bot_settings() -> None:
        if telegram_settings.enabled:
            telegram_status.setText("Останови Telegram worker перед изменением разрешений.")
            return
        persist_telegram_settings()

    save_telegram_token_button.clicked.connect(save_telegram_bot_token)
    save_telegram_settings_button.clicked.connect(save_telegram_bot_settings)
    telegram_enable_check.toggled.connect(toggle_telegram_worker)
    telegram_poll_timer.timeout.connect(reap_telegram_worker)
    telegram_poll_timer.start()
    startup_title = QLabel("АВТОЗАПУСК WINDOWS")
    startup_title.setStyleSheet("color:#c8cdd5; font-size:11px; letter-spacing:1.6px;")
    settings_layout.addWidget(startup_title)
    startup_check = QCheckBox("Запускать помощника при входе в Windows")
    startup_status = QLabel("Проверяю состояние Планировщика заданий…")
    startup_status.setWordWrap(True)
    startup_status.setStyleSheet("color:#929aa6;")
    settings_layout.addWidget(startup_check)
    settings_layout.addWidget(startup_status)
    launcher_path = install_root / "HellsaizLauncher.exe" if install_root is not None else None
    if launcher_path is None or not launcher_path.is_file():
        startup_check.setEnabled(False)
        startup_status.setText(
            "Автозапуск доступен только при запуске установленного приложения через HellsaizLauncher.exe."
        )
    else:
        try:
            startup_check.setChecked(startup_task.is_registered())
            startup_status.setText(
                "Планировщик заданий Windows управляет автозапуском. Уровень запуска: HIGHEST."
            )
        except startup_task.StartupTaskError as exc:
            startup_check.setEnabled(False)
            startup_status.setText(str(exc))

    startup_workers: list[QThread] = []

    def change_startup_task(enabled: bool) -> None:
        if launcher_path is None:
            startup_check.blockSignals(True)
            startup_check.setChecked(False)
            startup_check.blockSignals(False)
            startup_status.setText("Не найден стабильный HellsaizLauncher.exe.")
            return
        if any(worker.isRunning() for worker in startup_workers):
            return
        startup_check.setEnabled(False)
        startup_status.setText("Обновляю задачу Планировщика Windows…")
        worker = StartupTaskWorker(enabled, launcher_path)
        startup_workers.append(worker)

        def on_startup_completed(actual_state: bool, message: str) -> None:
            startup_check.blockSignals(True)
            startup_check.setChecked(actual_state)
            startup_check.blockSignals(False)
            startup_check.setEnabled(True)
            startup_status.setText(message)

        worker.completed.connect(on_startup_completed)
        worker.finished.connect(
            lambda: startup_workers.remove(worker) if worker in startup_workers else None
        )
        worker.start()

    startup_check.toggled.connect(change_startup_task)

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
        worker = UpdateWorker(
            settings.workflows_path.parent,
            current_app_version,
            install_root,
        )
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
        worker = UpdateWorker(
            settings.workflows_path.parent,
            current_app_version,
            install_root,
            download=True,
        )
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
    page_stack = AnimatedPageStack(duration_ms=160)
    page_stack.set_animations_enabled(bool(profile_data.get("animations_enabled", True)))
    navigation = QListWidget()
    navigation.setObjectName("mainNavigation")
    navigation.setAccessibleName("Основная навигация")
    navigation.setAccessibleDescription(
        "Разделы приложения. Используй стрелки вверх и вниз для переключения между разделами."
    )
    navigation.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    navigation.setTabKeyNavigation(True)
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
    animation_toggle = QCheckBox("Плавные переходы")
    animation_toggle.setAccessibleName("Плавные переходы между разделами")
    animation_toggle.setAccessibleDescription(
        "Включает или выключает короткое плавное появление страниц. "
        "Отключи, если предпочитаешь интерфейс без движения."
    )
    animation_toggle.setToolTip(
        "Короткое появление страницы при переключении. Можно отключить в любой момент."
    )
    animation_toggle.setChecked(bool(profile_data.get("animations_enabled", True)))

    def save_animation_preference(enabled: bool) -> None:
        profile_data["animations_enabled"] = bool(enabled)
        preference_path = settings.workflows_path.parent / "ai_profile.json"
        temporary = preference_path.with_suffix(".json.tmp")
        try:
            preference_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(profile_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(preference_path)
        except OSError:
            logging.exception("Could not persist the page animation preference")

    animation_toggle.toggled.connect(page_stack.set_animations_enabled)
    animation_toggle.toggled.connect(save_animation_preference)
    sidebar_layout.addWidget(animation_toggle)
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
    window.setStyleSheet(build_dark_stylesheet())

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
            tts_profile=active_tts,
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

    def run_scenario_from_studio(workflow_id: str, trigger_kind: str, trigger_value: str) -> None:
        if workers:
            scenario_status.setText(
                "Сейчас выполняется другая задача. Дождись её завершения и повтори запуск."
            )
            return
        start_worker(
            workflow_trigger=WorkflowTrigger(trigger_kind, trigger_value, workflow_id)
        )

    scenario_page.run_requested.connect(run_scenario_from_studio)

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
        worker_groups = (
            [wake_listener_state["worker"]],
            workers,
            update_workers,
            provider_health_workers,
            system_health_workers,
            startup_workers,
            network_workers,
            ocr_model_workers,
            voice_download_workers,
            vosk_model_download_workers,
            _BACKGROUND_VOICE_WORKERS["tests"],
            _BACKGROUND_VOICE_WORKERS["sapi_inventory"],
        )
        seen: set[int] = set()
        for group in worker_groups:
            for worker in tuple(group):
                if worker is None:
                    continue
                worker_id = id(worker)
                if worker_id in seen:
                    continue
                seen.add(worker_id)
                try:
                    if worker.isRunning():
                        logging.info(
                            "Waiting for background task %s to finish before exit",
                            type(worker).__name__,
                        )
                        worker.wait()
                except Exception:
                    logging.exception(
                        "Could not finish background task %s during shutdown",
                        type(worker).__name__,
                    )
        telegram_worker = telegram_worker_state.get("worker")
        if telegram_worker is not None and telegram_worker.is_alive():
            telegram_worker.stop()
            telegram_worker.join(timeout=33)
            if telegram_worker.is_alive():
                logging.error("Telegram worker did not stop before desktop shutdown timeout.")
        try:
            from hellsaiz_pc_ai.speech.vosk import VoskTranscriber
            from hellsaiz_pc_ai.speech.piper import PiperSynthesizer

            VoskTranscriber.clear_model_cache()
            PiperSynthesizer.clear_voice_cache()
        except Exception:
            logging.exception("Could not release cached speech models during shutdown")
        instance_lock.release()

    app.aboutToQuit.connect(stop_telegram_worker)
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
    if network_settings.get("launch_on_start") and network_settings.get("executable_path"):
        def start_network_client_on_launch() -> None:
            try:
                if not v2raytun.detect_v2raytun_running():
                    v2raytun.launch_v2raytun(network_settings["executable_path"])
                    network_status.setText(
                        "v2RayTun запущен автоматически. Подключи туннель в клиенте и проверь прокси."
                    )
            except Exception as exc:
                network_status.setText(f"Автозапуск v2RayTun не выполнен: {exc}")
        QTimer.singleShot(1200, start_network_client_on_launch)
    if telegram_settings.enabled:
        telegram_enable_check.blockSignals(True)
        telegram_enable_check.setChecked(True)
        telegram_enable_check.blockSignals(False)
        if not start_telegram_worker():
            telegram_settings.enabled = False
            telegram_enable_check.blockSignals(True)
            telegram_enable_check.setChecked(False)
            telegram_enable_check.blockSignals(False)
    def write_update_health_marker() -> None:
        if install_root is None:
            return
        try:
            marker = install_root / "health" / f"{current_app_version}.ok"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("ok", encoding="ascii")
            logging.info("Application startup health marker written for %s.", current_app_version)
        except OSError:
            logging.exception("Could not write update health marker")

    if install_root is not None:
        # Let Qt enter its event loop and process the first UI callbacks before
        # the updater considers this version healthy.
        QTimer.singleShot(1800, write_update_health_marker)
    QTimer.singleShot(0, poll_workflow_automations)
    QTimer.singleShot(0, poll_due_reminders)
    if auto_update_check.isChecked():
        QTimer.singleShot(1400, lambda: check_for_updates(True))
    workflow_timer.start()
    reminder_timer.start()
    return app.exec()

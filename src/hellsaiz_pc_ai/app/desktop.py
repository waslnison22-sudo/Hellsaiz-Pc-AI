from __future__ import annotations

import json
import logging
import tempfile
import threading
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
from hellsaiz_pc_ai.update_client import UpdateCheckError, check_latest_release
from hellsaiz_pc_ai.core.orchestrator import AssistantOrchestrator
from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.hotkeys import GlobalHotkeyService, HotkeyUnavailableError
from hellsaiz_pc_ai.providers.openai_compatible import OpenAICompatibleProvider, ProviderError
from hellsaiz_pc_ai.storage.reminders import ReminderStore
from hellsaiz_pc_ai.storage.sqlite_store import ChatStore
from hellsaiz_pc_ai.tools.clipboard import register_clipboard_tools
from hellsaiz_pc_ai.tools.reminders import register_reminder_tools
from hellsaiz_pc_ai.tools.system import register_system_tools
from hellsaiz_pc_ai.tools.windows import register_windows_tools
from hellsaiz_pc_ai.workflows.builder import append_hour_condition, append_repeat_action, append_tool_action, append_wait_action, append_weekday_condition, terminal_nodes
from hellsaiz_pc_ai.workflows.graph import WorkflowGraph, WorkflowGraphRunner, WorkflowTrigger
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary
from hellsaiz_pc_ai.workflows.scheduler import WorkflowScheduler


def build_runtime(settings: Settings):
    registry = ToolRegistry()
    register_system_tools(registry)

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
        from PySide6.QtGui import QDesktopServices, QFont
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
            QPushButton,
            QSplitter,
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
    (
        router, assistant, store, workflow_library, workflow_runner, registry,
        reminder_store, allowed_apps, profile_data
    ) = build_runtime(settings)
    active_voice = {"name": str(profile_data.get("voice_name") or settings.speech.tts_voice_name)}
    current_app_version = "0.1.0"

    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    window.setWindowTitle(settings.app_name)
    window.resize(1080, 760)
    window.setMinimumSize(860, 600)

    class ApprovalBroker(QObject):
        request = Signal(str, object, object)

        def __init__(self) -> None:
            super().__init__()
            self.request.connect(self._show)

        @Slot(str, object, object)
        def _show(self, name: str, arguments: object, response: object) -> None:
            result = QMessageBox.question(
                window,
                "Подтверждение действия",
                f"Разрешить инструменту {name} выполнить действие?\\nАргументы: {arguments}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            response["approved"] = result == QMessageBox.StandardButton.Yes
            response["event"].set()

        def confirm(self, spec: Any, arguments: dict[str, Any]) -> bool:
            response: dict[str, Any] = {"event": threading.Event(), "approved": False}
            self.request.emit(spec.name, arguments, response)
            return response["event"].wait(timeout=120) and bool(response["approved"])

    class HotkeyBridge(QObject):
        activated = Signal(str, str)

    class HotkeyDispatcher(QObject):
        def __init__(self, callback: Any) -> None:
            super().__init__()
            self.callback = callback

        @Slot(str, str)
        def dispatch(self, workflow_id: str, combo: str) -> None:
            self.callback(workflow_id, combo)

    class Worker(QThread):
        completed = Signal(str, str)
        failed = Signal(str)

        def __init__(
            self,
            prompt: str,
            voice_input: bool,
            speak_reply: bool,
            broker: ApprovalBroker,
            workflow_trigger: WorkflowTrigger | None = None,
        ) -> None:
            super().__init__()
            self.prompt = prompt
            self.voice_input = voice_input
            self.speak_reply = speak_reply
            self.broker = broker
            self.workflow_trigger = workflow_trigger

        def run(self) -> None:
            try:
                prompt = self.prompt
                if self.voice_input:
                    from hellsaiz_pc_ai.speech.capture import record_microphone
                    from hellsaiz_pc_ai.speech.vosk import VoskTranscriber

                    audio_path = Path(tempfile.gettempdir()) / "hellsaiz-command.wav"
                    record_microphone(audio_path, duration_seconds=5.0)
                    prompt = VoskTranscriber(settings.speech.vosk_model_path).transcribe(audio_path)
                if self.workflow_trigger is None and not prompt.strip():
                    self.failed.emit("Команда не распознана.")
                    return

                answer = None
                try:
                    trigger = self.workflow_trigger or WorkflowTrigger("text", prompt)
                    for workflow_id, graph in workflow_library.list():
                        if trigger.workflow_id is not None and workflow_id != trigger.workflow_id:
                            continue
                        execution = workflow_runner.run(
                            graph, trigger, confirm=self.broker.confirm
                        )
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
                        answer = router.route(prompt, confirm=self.broker.confirm)
                    if answer is None and assistant is not None:
                        answer = assistant.reply(prompt, confirm=self.broker.confirm)
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
                        from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer

                        Sapi5Synthesizer(
                            active_voice["name"],
                            settings.speech.tts_rate,
                            settings.speech.tts_volume,
                        ).speak(answer)
                    except Exception as exc:
                        logging.warning("Speech output unavailable: %s", exc)
                        answer += "\n\n[Голос недоступен: установите RHVoice и пакет voice.]"

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
        answer = QMessageBox.question(
            window,
            "Отменить напоминание",
            f"Отменить напоминание #{reminder_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
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
                "Пример создан. Сохрани его; Ctrl+Alt+H будет запускать действие с подтверждением."
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
        answer = QMessageBox.question(
            window, "Удалить сценарий", f"Удалить сценарий {workflow_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
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

        answer = QMessageBox.question(
            window,
            "Запустить сценарий",
            f"Выполнить сценарий «{graph.name}» сейчас?\n"
            "Опасные действия по-прежнему запросят отдельное подтверждение.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
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

    settings_page = QWidget()
    settings_layout = QVBoxLayout(settings_page)
    settings_layout.setContentsMargins(22, 20, 22, 20)
    settings_layout.setSpacing(12)
    settings_title = QLabel("НАСТРОЙКИ")
    settings_title.setStyleSheet("font-size:18px; font-weight:650; color:#f1f2f4;")
    settings_layout.addWidget(settings_title)
    settings_layout.addWidget(QLabel(f"История: {settings.database_path}"))
    settings_layout.addWidget(QLabel(f"Сценарии: {settings.workflows_path}"))

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

    auto_update_check = QCheckBox("Автоматически проверять обновления при запуске")
    auto_update_check.setChecked(bool(update_preferences.get("auto_check", True)))
    settings_layout.addWidget(auto_update_check)

    update_key_row = QHBoxLayout()
    update_key_input = QLineEdit()
    update_key_input.setEchoMode(QLineEdit.EchoMode.Password)
    update_key_input.setPlaceholderText("Ключ доступа к приватному каналу обновлений")
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
    open_release_button = QPushButton("Открыть релиз")
    open_release_button.setEnabled(False)
    update_buttons.addWidget(check_update_button)
    update_buttons.addWidget(open_release_button)
    settings_layout.addLayout(update_buttons)
    settings_layout.addStretch(1)
    tabs.addTab(settings_page, "Настройки")

    update_workers: list[QThread] = []
    latest_release_url = ""

    class UpdateWorker(QThread):
        checked = Signal(object)
        failed = Signal(str)

        def run(self) -> None:
            try:
                key_path = settings.workflows_path.parent / "update_key.dpapi"
                access_key = load_secret(key_path)
                result = check_latest_release(current_app_version, access_key)
                self.checked.emit(result)
            except (UpdateCheckError, SecureStoreError, OSError) as exc:
                self.failed.emit(str(exc))
            except Exception as exc:
                logging.exception("Update check failed")
                self.failed.emit(f"Ошибка проверки обновлений: {exc}")

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
        try:
            save_secret(key_path, update_key_input.text())
            update_key_input.clear()
            update_status.setText("Ключ защищён DPAPI и сохранён для текущей учётной записи Windows.")
        except SecureStoreError as exc:
            update_status.setText(str(exc))

    def check_for_updates(silent: bool = False) -> None:
        if any(worker.isRunning() for worker in update_workers):
            return
        update_status.setText("Проверяю канал обновлений…")
        worker = UpdateWorker()
        update_workers.append(worker)

        def on_checked(info: Any) -> None:
            nonlocal latest_release_url
            latest_release_url = info.release_url
            open_release_button.setEnabled(bool(latest_release_url))
            if info.update_available:
                if info.package_url and info.package_sha256:
                    update_status.setText(
                        f"Доступна версия {info.latest_version}. Windows-пакет опубликован; "
                        "доступна страница релиза для установки."
                    )
                else:
                    update_status.setText(
                        f"Доступна версия {info.latest_version}, но проверенный Windows-пакет "
                        "ещё не прикреплён к релизу."
                    )
            else:
                update_status.setText(f"Установлена последняя версия: {info.current_version}.")
            if not silent:
                logging.info("Update channel checked: latest=%s", info.latest_version)

        def on_failed(message: str) -> None:
            if not silent:
                update_status.setText(message)
            else:
                logging.info("Automatic update check: %s", message)

        worker.checked.connect(on_checked)
        worker.failed.connect(on_failed)
        worker.finished.connect(lambda: update_workers.remove(worker) if worker in update_workers else None)
        worker.start()

    auto_update_check.toggled.connect(lambda _: persist_update_preferences())
    save_update_key_button.clicked.connect(save_update_access_key)
    check_update_button.clicked.connect(lambda: check_for_updates(False))
    open_release_button.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl(latest_release_url)) if latest_release_url else None
    )

    window.setCentralWidget(tabs)
    window.setStyleSheet(
        "QMainWindow, QWidget { background:#090b0f; color:#e9ebef; font-family:'Segoe UI'; }"
        "QTabWidget::pane { border:0; background:#090b0f; }"
        "QTabBar::tab { background:transparent; color:#737b87; padding:10px 15px; "
        "margin:0 4px; border:0; border-radius:9px; }"
        "QTabBar::tab:selected { background:#191d24; color:#f4f5f7; }"
        "QTextEdit,QLineEdit,QPlainTextEdit,QComboBox,QListWidget { background:#11151b; "
        "color:#eef0f3; border:1px solid #252b34; border-radius:11px; padding:10px; "
        "selection-background-color:#414955; }"
        "QTextEdit { background:#0c0f14; border:0; padding:14px; }"
        "QLineEdit { min-height:24px; }"
        "QPushButton { background:#252a33; color:#e8ebef; border:1px solid #303743; "
        "border-radius:10px; padding:10px 14px; font-weight:550; }"
        "QPushButton:hover { background:#343b47; border-color:#46505f; }"
        "QPushButton#sendButton { background:#eceef1; color:#101318; border:0; "
        "font-weight:650; padding-left:18px; padding-right:18px; }"
        "QPushButton#sendButton:hover { background:#ffffff; }"
        "QPushButton#profileButton { background:#171b22; color:#c9ced6; border:1px solid #2c323c; }"
        "QPushButton#voiceButton { background:#171b22; color:#c9ced6; border:1px solid #2c323c; }"
        "QFrame#profilePanel { background:#11151b; border:1px solid #252b34; border-radius:13px; }"
        "QLabel { color:#d4d8df; }"
        "QCheckBox { color:#c7cbd2; spacing:8px; }"
        "QCheckBox::indicator { width:16px; height:16px; border:1px solid #686f7a; "
        "border-radius:4px; background:#111419; }"
        "QCheckBox::indicator:checked { background:#e7e9ed; border-color:#e7e9ed; }"
        "QSplitter::handle { background:#252b34; }"
    )

    broker = ApprovalBroker()
    workers: list[Worker] = []

    def start_worker(
        prompt: str = "",
        voice_input: bool = False,
        workflow_trigger: WorkflowTrigger | None = None,
    ) -> None:
        if workflow_trigger is None and not voice_input and not prompt.strip():
            return
        if voice_input and not settings.speech.vosk_model_path.is_dir():
            transcript.append(
                "<p style='color:#c5c9d0;'><b>Голос:</b> Сначала установите русскую модель "
                "Vosk и укажите speech.vosk_model_path в config.toml.</p>"
            )
            return
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
            broker,
            workflow_trigger,
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
        worker.start()

    def send() -> None:
        prompt = input_box.text().strip()
        input_box.clear()
        start_worker(prompt)

    send_button.clicked.connect(send)
    input_box.returnPressed.connect(send)
    voice_button.clicked.connect(lambda: start_worker(voice_input=True))

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
    QTimer.singleShot(0, poll_workflow_automations)
    QTimer.singleShot(0, poll_due_reminders)
    if auto_update_check.isChecked():
        QTimer.singleShot(1400, lambda: check_for_updates(True))
    workflow_timer.start()
    reminder_timer.start()
    return app.exec()

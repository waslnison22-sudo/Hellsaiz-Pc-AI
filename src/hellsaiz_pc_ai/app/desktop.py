from __future__ import annotations

import json
import logging
import tempfile
import threading
from html import escape
from pathlib import Path
from typing import Any

from hellsaiz_pc_ai.config import Settings, load_settings
from hellsaiz_pc_ai.core.commands import CommandRouter
from hellsaiz_pc_ai.core.orchestrator import AssistantOrchestrator
from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.hotkeys import GlobalHotkeyService, HotkeyUnavailableError
from hellsaiz_pc_ai.providers.openai_compatible import OpenAICompatibleProvider, ProviderError
from hellsaiz_pc_ai.storage.sqlite_store import ChatStore
from hellsaiz_pc_ai.tools.system import register_system_tools
from hellsaiz_pc_ai.tools.windows import register_windows_tools
from hellsaiz_pc_ai.workflows.builder import append_hour_condition, append_repeat_action, append_tool_action, append_wait_action, terminal_nodes
from hellsaiz_pc_ai.workflows.graph import WorkflowGraph, WorkflowGraphRunner, WorkflowTrigger
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary
from hellsaiz_pc_ai.workflows.scheduler import WorkflowScheduler


def build_runtime(settings: Settings):
    registry = ToolRegistry()
    register_system_tools(registry)
    register_windows_tools(registry, settings.allowed_apps, settings.allowed_processes)
    router = CommandRouter(registry, settings.allowed_apps, settings.allowed_processes)

    assistant = None
    if settings.llm.enabled:
        provider = OpenAICompatibleProvider(
            settings.llm.base_url,
            settings.llm.model,
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
    return router, assistant, store, workflow_library, workflow_runner, registry


def main() -> int:
    try:
        from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QFileDialog,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QMainWindow,
            QMessageBox,
            QPlainTextEdit,
            QPushButton,
            QSplitter,
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
    router, assistant, store, workflow_library, workflow_runner, registry = build_runtime(settings)

    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    window.setWindowTitle(settings.app_name)
    window.resize(1240, 820)
    window.setMinimumSize(900, 620)

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
                            settings.speech.tts_voice_name,
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
    home_layout.setContentsMargins(22, 20, 22, 18)
    home_layout.setSpacing(14)

    header = QLabel(
        "<div style='font-size:11px; letter-spacing:3px; color:#8e949e;'>HELLSAIZ / LOCAL DESKTOP</div>"
        "<div style='font-size:26px; font-weight:700; color:#f4f5f7;'>Hellsaiz PC AI</div>"
    )
    home_layout.addWidget(header)

    mode_text = "ЛОКАЛЬНЫЕ КОМАНДЫ · ИИ ВЫКЛЮЧЕН"
    if settings.llm.enabled:
        mode_text = f"ЛОКАЛЬНЫЕ КОМАНДЫ + LLM · {settings.llm.model}"
    status = QLabel(mode_text)
    status.setStyleSheet(
        "QLabel { color:#aab0ba; background:#111419; border:1px solid #292e37; "
        "border-radius:7px; padding:9px 12px; font-size:10px; letter-spacing:1.5px; }"
    )
    home_layout.addWidget(status)

    transcript = QTextEdit()
    transcript.setReadOnly(True)
    transcript.setPlaceholderText("Команды, ответы и история будут отображаться здесь.")
    transcript.append(
        "<p style='color:#b8bdc6;'>Система запущена в локальном режиме. "
        "Введите «помощь» для списка команд.</p>"
    )
    home_layout.addWidget(transcript, 1)

    controls = QHBoxLayout()
    input_box = QLineEdit()
    input_box.setPlaceholderText("Введите команду… например: открой блокнот")
    send_button = QPushButton("Выполнить")
    voice_button = QPushButton("Голос · 5 сек")
    speak_toggle = QCheckBox("Озвучивать ответы")
    speak_toggle.setChecked(settings.speech.auto_speak)
    controls.addWidget(input_box, 1)
    controls.addWidget(send_button)
    controls.addWidget(voice_button)
    home_layout.addLayout(controls)
    home_layout.addWidget(speak_toggle)
    tabs.addTab(home_page, "Главная")

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

    companion_page = QWidget()
    companion_layout = QVBoxLayout(companion_page)
    companion_title = QLabel("3D-КОМПАНЬОН")
    companion_title.setStyleSheet("font-size:18px; font-weight:650; color:#f1f2f4;")
    companion_layout.addWidget(companion_title)
    companion_status = QLabel(
        "Основной персонаж закреплён по твоему референсу: тёмные волосы, чёрная маска, "
        "белая рубашка и чёрные ремни. Случайные модели не подставляются."
    )
    companion_status.setWordWrap(True)
    companion_status.setStyleSheet(
        "background:#111419; border:1px solid #303641; border-radius:10px; "
        "padding:18px; color:#c9cdd4;"
    )
    companion_layout.addWidget(companion_status)
    companion_asset = QLabel("3D-файл пока не подключён. Рендерер VRM/Live2D ещё не добавлен.")
    companion_asset.setWordWrap(True)
    companion_layout.addWidget(companion_asset)
    companion_pick = QPushButton("Выбрать файл модели…")
    companion_layout.addWidget(companion_pick)

    def choose_companion_asset() -> None:
        path, _ = QFileDialog.getOpenFileName(
            window,
            "Выбрать модель персонажа",
            str(Path.home()),
            "3D/Live2D models (*.vrm *.glb *.gltf *.model3.json)",
        )
        if not path:
            return
        selected = Path(path)
        if not selected.is_file() or selected.stat().st_size > 250 * 1024 * 1024:
            companion_asset.setText("Файл отсутствует или превышает 250 МБ.")
            return
        settings.workflows_path.parent.mkdir(parents=True, exist_ok=True)
        companion_config = settings.workflows_path.parent / "companion.json"
        companion_config.write_text(
            json.dumps({"asset_path": str(selected)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        companion_asset.setText(
            f"Файл выбран: {selected.name}. Для отображения модели ещё нужен 3D-рендерер."
        )

    companion_pick.clicked.connect(choose_companion_asset)
    companion_layout.addStretch(1)
    tabs.addTab(companion_page, "Компаньон")

    voice_page = QWidget()
    voice_layout = QVBoxLayout(voice_page)
    voice_title = QLabel("ГОЛОС / OFFLINE STT + TTS")
    voice_title.setStyleSheet("font-size:18px; font-weight:650; color:#f1f2f4;")
    voice_layout.addWidget(voice_title)
    voice_info = QLabel(
        f"STT-модель Vosk: {settings.speech.vosk_model_path}\n"
        f"Путь существует: {'да' if settings.speech.vosk_model_path.is_dir() else 'нет'}"
    )
    voice_info.setWordWrap(True)
    voice_info.setStyleSheet("color:#b6bdc8;")
    voice_layout.addWidget(voice_info)
    voice_combo = QComboBox()
    voice_combo.setMinimumWidth(300)
    voice_layout.addWidget(voice_combo)
    voice_buttons = QHBoxLayout()
    refresh_voices_button = QPushButton("Найти голоса Windows")
    test_voice_button = QPushButton("Проверить голос")
    voice_buttons.addWidget(refresh_voices_button)
    voice_buttons.addWidget(test_voice_button)
    voice_layout.addLayout(voice_buttons)
    voice_status = QLabel(
        "Рекомендуемый голос: RHVoice Aleksandr через Windows SAPI5. "
        "Голосовые команды распознаются через локальную модель Vosk."
    )
    voice_status.setWordWrap(True)
    voice_status.setStyleSheet("color:#b6bdc8;")
    voice_layout.addWidget(voice_status)
    voice_layout.addStretch(1)

    def refresh_voices() -> None:
        try:
            from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer

            voices = Sapi5Synthesizer().list_voices()
            voice_combo.clear()
            for voice in voices:
                voice_combo.addItem(voice.name, voice.id)
            preferred = voice_combo.findText(settings.speech.tts_voice_name)
            if preferred >= 0:
                voice_combo.setCurrentIndex(preferred)
            voice_status.setText(
                f"Найдено голосов Windows: {len(voices)}. "
                "Выбери установленный русский голос RHVoice."
            )
        except Exception as exc:
            voice_status.setText(f"Не удалось получить список SAPI5: {exc}")

    def test_voice() -> None:
        voice_name = voice_combo.currentText()
        if not voice_name:
            voice_status.setText("Сначала найди установленные голоса Windows.")
            return
        try:
            from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer

            Sapi5Synthesizer(
                voice_name, settings.speech.tts_rate, settings.speech.tts_volume
            ).speak("Hellsaiz PC AI. Проверка локального русского голоса.")
            voice_status.setText(f"Проверка завершена: {voice_name}.")
        except Exception as exc:
            voice_status.setText(f"Не удалось воспроизвести голос: {exc}")

    refresh_voices_button.clicked.connect(refresh_voices)
    test_voice_button.clicked.connect(test_voice)
    tabs.addTab(voice_page, "Голос")

    commands_page = QWidget()
    commands_layout = QVBoxLayout(commands_page)
    commands_title = QLabel("ЗАРЕГИСТРИРОВАННЫЕ ИНСТРУМЕНТЫ")
    commands_title.setStyleSheet("font-size:18px; font-weight:650; color:#f1f2f4;")
    commands_layout.addWidget(commands_title)
    tool_list = QListWidget()
    for tool in registry.openai_schemas():
        function = tool["function"]
        tool_list.addItem(f"{function['name']} — {function['description']}")
    commands_layout.addWidget(tool_list)
    commands_hint = QLabel(
        "Инструменты вызываются через локальные правила или сценарии. "
        "Изменяющие действия всегда запрашивают подтверждение."
    )
    commands_hint.setWordWrap(True)
    commands_hint.setStyleSheet("color:#aab0ba;")
    commands_layout.addWidget(commands_hint)
    tabs.addTab(commands_page, "Команды")

    plugins_page = QWidget()
    plugins_layout = QVBoxLayout(plugins_page)
    plugins_title = QLabel("ПЛАГИНЫ")
    plugins_title.setStyleSheet("font-size:18px; font-weight:650; color:#f1f2f4;")
    plugins_layout.addWidget(plugins_title)
    plugins_hint = QLabel(
        "Система расширений проектируется на локальных модулях с явными разрешениями. "
        "Загрузка произвольных Python-файлов отключена."
    )
    plugins_hint.setWordWrap(True)
    plugins_hint.setStyleSheet("color:#b6bdc8;")
    plugins_layout.addWidget(plugins_hint)
    plugins_layout.addStretch(1)
    tabs.addTab(plugins_page, "Плагины")

    settings_page = QWidget()
    settings_layout = QVBoxLayout(settings_page)
    settings_title = QLabel("НАСТРОЙКИ")
    settings_title.setStyleSheet("font-size:18px; font-weight:650; color:#f1f2f4;")
    settings_layout.addWidget(settings_title)
    settings_layout.addWidget(QLabel("Цветовая схема: чёрный / графит / серый / белый."))
    settings_layout.addWidget(QLabel(f"Локальная LLM: {'включена' if settings.llm.enabled else 'выключена'}"))
    settings_layout.addWidget(QLabel(f"История: {settings.database_path}"))
    settings_layout.addWidget(QLabel(f"Сценарии: {settings.workflows_path}"))
    settings_layout.addStretch(1)
    tabs.addTab(settings_page, "Настройки")

    window.setCentralWidget(tabs)
    window.setStyleSheet(
        "QMainWindow, QWidget { background:#08090c; color:#eceef2; font-family:'Segoe UI'; }"
        "QTextEdit,QLineEdit,QPlainTextEdit,QComboBox,QListWidget { background:#101318; "
        "color:#f0f1f4; border:1px solid #2b3039; border-radius:9px; padding:10px; "
        "selection-background-color:#626a76; }"
        "QTextEdit,QPlainTextEdit { font-size:13px; }"
        "QLineEdit { min-height:24px; }"
        "QPushButton { background:#e7e9ed; color:#111318; border:0; border-radius:8px; "
        "padding:10px 16px; font-weight:600; }"
        "QPushButton:hover { background:#ffffff; }"
        "QPushButton:disabled { background:#40454d; color:#9298a2; }"
        "QCheckBox { color:#c7cbd2; spacing:8px; }"
        "QCheckBox::indicator { width:16px; height:16px; border:1px solid #686f7a; "
        "border-radius:4px; background:#111419; }"
        "QCheckBox::indicator:checked { background:#e7e9ed; border-color:#e7e9ed; }"
        "QTabWidget::pane { border:1px solid #292e37; border-radius:8px; }"
        "QTabBar::tab { background:#111419; color:#9ea5b0; padding:11px 16px; "
        "margin-right:3px; border-top-left-radius:7px; border-top-right-radius:7px; }"
        "QTabBar::tab:selected { background:#252b34; color:#ffffff; }"
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
        worker.failed.connect(
            lambda message: transcript.append(
                f"<p style='color:#c5c9d0;'><b>Ошибка:</b> {escape(message)}</p>"
            )
        )
        worker.finished.connect(lambda: send_button.setEnabled(True))
        worker.finished.connect(lambda: voice_button.setEnabled(True))
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

    # Trigger startup workflows only after the main window enters the Qt event loop.
    window.show()
    QTimer.singleShot(0, poll_workflow_automations)
    workflow_timer.start()
    return app.exec()

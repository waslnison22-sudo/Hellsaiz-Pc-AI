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
from hellsaiz_pc_ai.providers.openai_compatible import OpenAICompatibleProvider, ProviderError
from hellsaiz_pc_ai.storage.sqlite_store import ChatStore
from hellsaiz_pc_ai.tools.system import register_system_tools
from hellsaiz_pc_ai.tools.windows import register_windows_tools
from hellsaiz_pc_ai.workflows.graph import WorkflowGraph, WorkflowGraphRunner, WorkflowTrigger
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary


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
        from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
        from PySide6.QtGui import QBrush, QColor, QFont, QPen
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QFileDialog,
            QGraphicsScene,
            QGraphicsView,
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
                f"Разрешить инструменту {name} выполнить действие?\nАргументы: {arguments}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            response["approved"] = result == QMessageBox.StandardButton.Yes
            response["event"].set()

        def confirm(self, spec: Any, arguments: dict[str, Any]) -> bool:
            response: dict[str, Any] = {"event": threading.Event(), "approved": False}
            self.request.emit(spec.name, arguments, response)
            return response["event"].wait(timeout=120) and bool(response["approved"])

    class Worker(QThread):
        completed = Signal(str, str)
        failed = Signal(str)

        def __init__(
            self, prompt: str, voice_input: bool, speak_reply: bool, broker: ApprovalBroker
        ) -> None:
            super().__init__()
            self.prompt = prompt
            self.voice_input = voice_input
            self.speak_reply = speak_reply
            self.broker = broker

        def run(self) -> None:
            try:
                prompt = self.prompt
                if self.voice_input:
                    from hellsaiz_pc_ai.speech.capture import record_microphone
                    from hellsaiz_pc_ai.speech.vosk import VoskTranscriber

                    audio_path = Path(tempfile.gettempdir()) / "hellsaiz-command.wav"
                    record_microphone(audio_path, duration_seconds=5.0)
                    prompt = VoskTranscriber(settings.speech.vosk_model_path).transcribe(audio_path)
                if not prompt.strip():
                    self.failed.emit("Команда не распознана.")
                    return

                answer = None
                try:
                    for workflow_id, graph in workflow_library.list():
                        execution = workflow_runner.run(
                            graph, WorkflowTrigger("text", prompt), confirm=self.broker.confirm
                        )
                        if execution.started:
                            lines = [
                                f"Сценарий «{graph.name}» ({workflow_id}): {execution.message}"
                            ]
                            lines.extend(
                                f"• {step.output}" for step in execution.steps
                            )
                            answer = "\n".join(lines)
                            break
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    logging.warning("Workflow library could not be fully loaded: %s", exc)

                if answer is None:
                    answer = router.route(prompt, confirm=self.broker.confirm)
                if answer is None and assistant is not None:
                    answer = assistant.reply(prompt, confirm=self.broker.confirm)
                elif answer is None:
                    answer = (
                        "Эта фраза пока не входит в список локальных команд. "
                        "Введите «помощь», чтобы увидеть доступные команды. "
                        "Генеративный ИИ выключен."
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

                store.add_message("user", prompt)
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
        "Связывай триггеры, условия и действия. Проверка выполняется до сохранения; "
        "произвольный код не поддерживается."
    )
    scenario_hint.setStyleSheet("color:#aab0ba;")
    scenario_layout.addWidget(scenario_hint)

    scenario_workspace = QHBoxLayout()
    scenario_list = QListWidget()
    scenario_list.setMinimumWidth(190)
    scenario_workspace.addWidget(scenario_list, 1)

    scenario_splitter = QSplitter(Qt.Orientation.Horizontal)
    graph_scene = QGraphicsScene()
    graph_view = QGraphicsView(graph_scene)
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

    scenario_id = QLineEdit()
    scenario_id.setPlaceholderText("id-сценария, например night-mode")
    scenario_layout.addWidget(scenario_id)
    scenario_buttons = QHBoxLayout()
    new_scenario_button = QPushButton("Новый")
    validate_scenario_button = QPushButton("Проверить граф")
    save_scenario_button = QPushButton("Сохранить")
    delete_scenario_button = QPushButton("Удалить")
    scenario_buttons.addWidget(new_scenario_button)
    scenario_buttons.addWidget(validate_scenario_button)
    scenario_buttons.addWidget(save_scenario_button)
    scenario_buttons.addWidget(delete_scenario_button)
    scenario_layout.addLayout(scenario_buttons)
    scenario_status = QLabel("Сценарии хранятся локально в JSON.")
    scenario_status.setStyleSheet("color:#aab0ba;")
    scenario_layout.addWidget(scenario_status)

    def render_graph(graph: WorkflowGraph) -> None:
        graph_scene.clear()
        positions = {
            node.id: ((index % 3) * 290, (index // 3) * 150)
            for index, node in enumerate(graph.nodes)
        }
        by_id = {node.id: node for node in graph.nodes}
        for edge in graph.edges:
            x1, y1 = positions[edge.source]
            x2, y2 = positions[edge.target]
            start_x, start_y = x1 + 220, y1 + 36
            end_x, end_y = x2, y2 + 36
            graph_scene.addLine(
                start_x, start_y, end_x, end_y, QPen(QColor("#777f8a"), 2)
            )
            if edge.when:
                label = graph_scene.addText(edge.when.upper())
                label.setDefaultTextColor(QColor("#c9cdd4"))
                label.setPos((start_x + end_x) / 2, (start_y + end_y) / 2 - 18)
        for node in graph.nodes:
            x, y = positions[node.id]
            graph_scene.addRect(
                x, y, 220, 72,
                QPen(QColor("#848c98"), 1.4),
                QBrush(QColor("#171b22")),
            )
            title = graph_scene.addText(node.id)
            title.setDefaultTextColor(QColor("#f4f5f7"))
            title.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            title.setPos(x + 12, y + 8)
            kind = graph_scene.addText(node.kind)
            kind.setDefaultTextColor(QColor("#abb2bd"))
            kind.setPos(x + 12, y + 36)
        graph_scene.setSceneRect(graph_scene.itemsBoundingRect().adjusted(-35, -35, 35, 35))

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
            render_graph(graph)
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
            render_graph(WorkflowGraph.from_dict(example))
            scenario_status.setText("Пример создан. Проверь и сохрани его.")
        except ValueError as exc:
            scenario_status.setText(str(exc))

    def validate_scenario() -> WorkflowGraph | None:
        try:
            graph = WorkflowGraph.from_dict(json.loads(graph_editor.toPlainText()))
            render_graph(graph)
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
            refresh_scenario_list()
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
            scenario_status.setText(f"Сценарий {workflow_id} удалён.")

    new_scenario_button.clicked.connect(create_scenario)
    validate_scenario_button.clicked.connect(validate_scenario)
    save_scenario_button.clicked.connect(save_scenario)
    delete_scenario_button.clicked.connect(delete_scenario)
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

    def start_worker(prompt: str = "", voice_input: bool = False) -> None:
        if not voice_input and not prompt.strip():
            return
        if voice_input and not settings.speech.vosk_model_path.is_dir():
            transcript.append(
                "<p style='color:#c5c9d0;'><b>Голос:</b> Сначала установите русскую модель "
                "Vosk и укажите speech.vosk_model_path в config.toml.</p>"
            )
            return
        if prompt:
            transcript.append(f"<p><b>Вы:</b> {escape(prompt)}</p>")
        send_button.setEnabled(False)
        voice_button.setEnabled(False)
        worker = Worker(prompt, voice_input, speak_toggle.isChecked(), broker)
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
        worker.finished.connect(lambda: workers.remove(worker) if worker in workers else None)
        worker.start()

    def send() -> None:
        prompt = input_box.text().strip()
        input_box.clear()
        start_worker(prompt)

    send_button.clicked.connect(send)
    input_box.returnPressed.connect(send)
    voice_button.clicked.connect(lambda: start_worker(voice_input=True))

    window.show()
    return app.exec()

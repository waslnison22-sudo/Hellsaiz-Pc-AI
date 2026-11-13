from __future__ import annotations

import logging
import threading
from html import escape
from typing import Any

from hellsaiz_pc_ai.config import load_settings
from hellsaiz_pc_ai.core.orchestrator import AssistantOrchestrator
from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.providers.openai_compatible import OpenAICompatibleProvider, ProviderError
from hellsaiz_pc_ai.storage.sqlite_store import ChatStore
from hellsaiz_pc_ai.tools.system import register_system_tools
from hellsaiz_pc_ai.tools.windows import register_windows_tools


def build_assistant() -> tuple[AssistantOrchestrator, ChatStore]:
    settings = load_settings()
    provider = OpenAICompatibleProvider(
        settings.llm.base_url, settings.llm.model, settings.llm.api_key,
        settings.llm.timeout_seconds, settings.allow_remote_llm,
    )
    registry = ToolRegistry()
    register_system_tools(registry)
    register_windows_tools(registry, settings.allowed_apps)
    assistant = AssistantOrchestrator(
        provider, registry, settings.llm.system_prompt, settings.llm.max_tool_rounds
    )
    store = ChatStore(settings.database_path)
    assistant.history = store.recent_messages()
    return assistant, store


def main() -> int:
    try:
        from PySide6.QtCore import QObject, QThread, Signal, Slot
        from PySide6.QtWidgets import (
            QApplication, QHBoxLayout, QLineEdit, QMainWindow, QMessageBox,
            QPushButton, QTextEdit, QVBoxLayout, QWidget,
        )
    except ImportError:
        print("PySide6 is missing. Run: pip install -e .")
        return 2

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    try:
        assistant, store = build_assistant()
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 2

    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    window.setWindowTitle(settings.app_name)
    window.resize(900, 650)
    window.setMinimumSize(620, 460)

    class ApprovalBroker(QObject):
        request = Signal(str, object, object)

        def __init__(self) -> None:
            super().__init__()
            self.request.connect(self._show)

        @Slot(str, object, object)
        def _show(self, name: str, arguments: object, response: object) -> None:
            result = QMessageBox.question(
                window, "Подтверждение действия",
                f"Разрешить инструменту {name} выполнить действие?\nАргументы: {arguments}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            response["approved"] = result == QMessageBox.StandardButton.Yes
            response["event"].set()

        def confirm(self, spec: Any, arguments: dict[str, Any]) -> bool:
            response: dict[str, Any] = {"event": threading.Event(), "approved": False}
            self.request.emit(spec.name, arguments, response)
            response["event"].wait(timeout=120)
            return bool(response["approved"])

    class Worker(QThread):
        completed = Signal(str)
        failed = Signal(str)

        def __init__(self, prompt: str, broker: ApprovalBroker) -> None:
            super().__init__()
            self.prompt, self.broker = prompt, broker

        def run(self) -> None:
            try:
                answer = assistant.reply(self.prompt, confirm=self.broker.confirm)
                store.add_message("user", self.prompt)
                store.add_message("assistant", answer)
                self.completed.emit(answer)
            except ProviderError as exc:
                self.failed.emit(str(exc))
            except Exception:
                logging.exception("Unhandled assistant error")
                self.failed.emit("Внутренняя ошибка. Подробности записаны в локальный лог.")

    central = QWidget()
    layout = QVBoxLayout(central)
    transcript = QTextEdit()
    transcript.setReadOnly(True)
    transcript.append(
        f"<b>{escape(settings.app_name)}</b><br>Модель: {escape(settings.llm.model)}"
        f"<br>Локальный сервер: {escape(settings.llm.base_url)}"
    )
    layout.addWidget(transcript)
    row = QHBoxLayout()
    input_box = QLineEdit()
    input_box.setPlaceholderText("Напишите запрос…")
    send_button = QPushButton("Отправить")
    row.addWidget(input_box, 1)
    row.addWidget(send_button)
    layout.addLayout(row)
    window.setCentralWidget(central)
    window.setStyleSheet(
        "QMainWindow, QWidget { background:#0b0d11; color:#e7e9ee; }"
        "QTextEdit,QLineEdit { background:#131720; color:#f4f5f7; border:1px solid #303746;"
        " border-radius:8px; padding:10px; }"
        "QPushButton { background:#252c38; color:white; border:0; border-radius:8px; padding:10px 18px; }"
        "QPushButton:hover { background:#343e50; }"
    )
    broker = ApprovalBroker()
    workers: list[Worker] = []

    def send() -> None:
        prompt = input_box.text().strip()
        if not prompt:
            return
        input_box.clear()
        transcript.append(f"<p><b>Вы:</b> {escape(prompt)}</p>")
        send_button.setEnabled(False)
        worker = Worker(prompt, broker)
        workers.append(worker)
        worker.completed.connect(lambda text: transcript.append(f"<p><b>Hellsaiz:</b> {escape(text)}</p>"))
        worker.failed.connect(lambda text: transcript.append(f"<p><b>Ошибка:</b> {escape(text)}</p>"))
        worker.finished.connect(lambda: send_button.setEnabled(True))
        worker.finished.connect(lambda: workers.remove(worker) if worker in workers else None)
        worker.start()

    send_button.clicked.connect(send)
    input_box.returnPressed.connect(send)
    window.show()
    return app.exec()

from __future__ import annotations

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


def build_runtime(settings: Settings):
    registry = ToolRegistry()
    register_system_tools(registry)
    register_windows_tools(registry, settings.allowed_apps)
    router = CommandRouter(registry, settings.allowed_apps)

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
    return router, assistant, store


def main() -> int:
    try:
        from PySide6.QtCore import QObject, QThread, Signal, Slot
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
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
    router, assistant, store = build_runtime(settings)

    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    window.setWindowTitle(settings.app_name)
    window.resize(1080, 720)
    window.setMinimumSize(760, 540)

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

    central = QWidget()
    layout = QVBoxLayout(central)
    layout.setContentsMargins(22, 20, 22, 18)
    layout.setSpacing(14)

    header = QLabel(
        "<div style='font-size:11px; letter-spacing:3px; color:#8e949e;'>HELLSAIZ / LOCAL DESKTOP</div>"
        "<div style='font-size:26px; font-weight:700; color:#f4f5f7;'>Hellsaiz PC AI</div>"
    )
    layout.addWidget(header)

    mode_text = "ЛОКАЛЬНЫЕ КОМАНДЫ · ИИ ВЫКЛЮЧЕН"
    if settings.llm.enabled:
        mode_text = f"ЛОКАЛЬНЫЕ КОМАНДЫ + LLM · {settings.llm.model}"
    status = QLabel(mode_text)
    status.setStyleSheet(
        "QLabel { color:#aab0ba; background:#111419; border:1px solid #292e37; "
        "border-radius:7px; padding:9px 12px; font-size:10px; letter-spacing:1.5px; }"
    )
    layout.addWidget(status)

    transcript = QTextEdit()
    transcript.setReadOnly(True)
    transcript.setPlaceholderText("Команды, ответы и история будут отображаться здесь.")
    transcript.append(
        "<p style='color:#b8bdc6;'>Система запущена в локальном режиме. "
        "Введите «помощь» для списка команд.</p>"
    )
    layout.addWidget(transcript, 1)

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
    layout.addLayout(controls)
    layout.addWidget(speak_toggle)

    window.setCentralWidget(central)
    window.setStyleSheet(
        "QMainWindow, QWidget { background:#08090c; color:#eceef2; font-family:'Segoe UI'; }"
        "QTextEdit,QLineEdit { background:#101318; color:#f0f1f4; border:1px solid #2b3039;"
        " border-radius:9px; padding:12px; selection-background-color:#777e88; }"
        "QTextEdit { font-size:14px; }"
        "QLineEdit { font-size:14px; min-height:24px; }"
        "QPushButton { background:#e7e9ed; color:#111318; border:0; border-radius:8px;"
        " padding:10px 16px; font-weight:600; }"
        "QPushButton:hover { background:#ffffff; }"
        "QPushButton:disabled { background:#40454d; color:#9298a2; }"
        "QCheckBox { color:#c7cbd2; spacing:8px; }"
        "QCheckBox::indicator { width:16px; height:16px; border:1px solid #686f7a;"
        " border-radius:4px; background:#111419; }"
        "QCheckBox::indicator:checked { background:#e7e9ed; border-color:#e7e9ed; }"
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

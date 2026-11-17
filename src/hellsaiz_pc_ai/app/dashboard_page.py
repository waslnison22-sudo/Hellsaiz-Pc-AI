from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hellsaiz_pc_ai.tools.public_info import get_weather

from hellsaiz_pc_ai.app.dashboard_texts import (
    QUICK_COMMANDS,
    greeting_for_hour,
    greeting_note,
    preview_reminders,
)

class WeatherWorker(QThread):
    """Fetches one open-meteo weather line for the dashboard card."""

    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, city: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.city = city

    def run(self) -> None:
        try:
            self.completed.emit(get_weather(self.city))
        except Exception as exc:
            self.failed.emit(str(exc))


class DashboardPage(QWidget):
    """Astra-style home page: greeting, weather, reminders, quick commands, system."""

    def __init__(
        self,
        *,
        reminder_store: Any,
        assistant_persona: str = "хеллсайз",
        version: str = "",
        city: str = "Ставрополь",
        on_send: Callable[[str], None] | None = None,
        on_open_diagnostics: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._reminder_store = reminder_store
        self._city = city
        self._on_send = on_send or (lambda command: None)
        self._on_open_diagnostics = on_open_diagnostics or (lambda: None)
        self._weather_fetch_started = False
        self._weather_worker: WeatherWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(14)

        now = datetime.now()
        greeting_label = QLabel(greeting_for_hour(now.hour))
        greeting_label.setObjectName("dashboardGreeting")
        greeting_label.setStyleSheet("font-size:26px; font-weight:700; color:#f4f7fb;")
        layout.addWidget(greeting_label)
        note_label = QLabel(greeting_note(now.hour, assistant_persona))
        note_label.setStyleSheet("color:#aab3c0; font-size:13px;")
        layout.addWidget(note_label)
        meta_label = QLabel(now.strftime("%A, %d.%m.%Y %H:%M") + (f"  ·  v{version}" if version else ""))
        meta_label.setStyleSheet("color:#8e98a6; font-size:12px;")
        layout.addWidget(meta_label)

        grid = QGridLayout()
        grid.setSpacing(12)
        layout.addLayout(grid, 1)

        weather_value = self._make_card(grid, 0, 0, "Погода", self._city, "Нажми «Обновить».")
        self._weather_text = weather_value
        refresh_weather_button = QPushButton("Обновить")
        refresh_weather_button.setToolTip("Запросить погоду ещё раз")
        refresh_weather_button.clicked.connect(self._start_weather_fetch)
        grid.addWidget(refresh_weather_button, 0, 0, 2, 1, Qt.AlignmentFlag.AlignBottom)

        self._reminders_list = self._make_card_list(grid, 0, 1, "Напоминания")
        self.refresh_reminders()

        self._make_card(grid, 1, 0, "Система", f"Версия {version or '-'}", "")
        diagnostics_button = QPushButton("Диагностика")
        diagnostics_button.setObjectName("secondaryButton")
        diagnostics_button.setToolTip("Проверка голоса, базы, сценариев и хранилища")
        diagnostics_button.clicked.connect(lambda: self._on_open_diagnostics())
        grid.addWidget(diagnostics_button, 1, 0, 2, 1, Qt.AlignmentFlag.AlignBottom)

        commands_panel = self._make_card_frame(grid, 1, 1, "Быстрые команды")
        commands_layout = commands_panel.layout()
        commands_row = QHBoxLayout()
        commands_row.setSpacing(6)
        for command in QUICK_COMMANDS:
            button = QPushButton(command)
            button.setToolTip("Запустить команду сразу")
            button.clicked.connect(lambda _=False, cmd=command: self._on_send(cmd))
            commands_row.addWidget(button)
        commands_layout.addLayout(commands_row, 1)

    def _make_card_frame(self, grid: QGridLayout, row: int, column: int, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("dashboardCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("dashboardCardTitle")
        card_layout.addWidget(title_label)
        grid.addWidget(card, row, column)
        return card

    def _make_card(
        self,
        grid: QGridLayout,
        row: int,
        column: int,
        title: str,
        value: str,
        note: str,
    ) -> QLabel:
        card = self._make_card_frame(grid, row, column, title)
        value_label = QLabel(value)
        value_label.setObjectName("dashboardCardValue")
        value_label.setWordWrap(True)
        card.layout().addWidget(value_label, 1)
        if note:
            note_label = QLabel(note)
            note_label.setObjectName("dashboardCardNote")
            note_label.setWordWrap(True)
            card.layout().addWidget(note_label)
        return value_label

    def _make_card_list(self, grid: QGridLayout, row: int, column: int, title: str) -> QListWidget:
        card = self._make_card_frame(grid, row, column, title)
        list_widget = QListWidget()
        card.layout().addWidget(list_widget, 1)
        return list_widget

    def refresh_reminders(self) -> None:
        self._reminders_list.clear()
        try:
            entries = self._reminder_store.list_pending()
        except (OSError, ValueError):
            self._reminders_list.addItem("Не удалось загрузить напоминания.")
            return
        lines = preview_reminders(list(entries))
        if not lines:
            self._reminders_list.addItem("Активных напоминаний нет.")
        for line in lines:
            self._reminders_list.addItem(line)

    def _start_weather_fetch(self) -> None:
        if self._weather_worker is not None and self._weather_worker.isRunning():
            return
        self._weather_text.setText(f"Загружаю погоду для {self._city}…")
        worker = WeatherWorker(self._city)
        self._weather_worker = worker

        def on_completed(answer: str) -> None:
            self._weather_text.setText(answer)

        def on_failed(message: str) -> None:
            self._weather_text.setText(f"Погода сейчас недоступна: {message}")

        worker.completed.connect(on_completed)
        worker.failed.connect(on_failed)
        worker.finished.connect(
            lambda: self._weather_workers_clear(worker)
        )
        worker.start()

    def _weather_workers_clear(self, worker: WeatherWorker) -> None:
        if self._weather_worker is worker:
            self._weather_worker = None

    def showEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        if not self._weather_fetch_started:
            self._weather_fetch_started = True
            QTimer.singleShot(300, self._start_weather_fetch)

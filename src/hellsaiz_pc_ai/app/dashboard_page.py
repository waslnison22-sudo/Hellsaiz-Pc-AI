from __future__ import annotations
import logging

from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from hellsaiz_pc_ai.tools.public_info import WeatherReport, get_weather_report

from hellsaiz_pc_ai.app.ui_icons import refresh_icon
from hellsaiz_pc_ai.app.dashboard_texts import (
    greeting_for_hour,
    greeting_note,
    preview_reminders,
)
from hellsaiz_pc_ai.app.hud_components import EmptyState

class WeatherWorker(QThread):
    """Fetches the Open-Meteo report (current, hourly slice, five days)."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, city: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.city = city

    def run(self) -> None:
        try:
            self.completed.emit(get_weather_report(self.city))
        except Exception as exc:
            self.failed.emit(str(exc))


def _temperature_text(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = round(value)
    return f"{'+' if rounded > 0 else ''}{rounded}°"


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
        on_city_change: Callable[[str], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._reminder_store = reminder_store
        self._city = city
        self._on_send = on_send or (lambda command: None)
        self._on_open_diagnostics = on_open_diagnostics or (lambda: None)
        self._on_city_change = on_city_change
        self._weather_fetch_started = False
        self._weather_finished = False
        self._weather_worker: WeatherWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(14)
        logging.info("DashboardPage ctor: entered.")

        now = datetime.now()
        greeting_label = QLabel(greeting_for_hour(now.hour))
        greeting_label.setObjectName("dashboardGreeting")
        greeting_label.setStyleSheet("font-size:26px; font-weight:700; color:#F2EFEA;")
        layout.addWidget(greeting_label)
        note_label = QLabel(greeting_note(now.hour, assistant_persona))
        note_label.setStyleSheet("color:#A6A29C; font-size:13px;")
        layout.addWidget(note_label)
        weekdays_ru = (
            "Понедельник", "Вторник", "Среда", "Четверг",
            "Пятница", "Суббота", "Воскресенье",
        )
        meta_text = f"{weekdays_ru[now.weekday()]}, {now:%d.%m.%Y %H:%M}"
        meta_label = QLabel(meta_text + (f"  ·  v{version}" if version else ""))
        meta_label.setStyleSheet("color:#A6A29C; font-size:12px;")
        layout.addWidget(meta_label)

        grid = QGridLayout()
        grid.setSpacing(12)
        layout.addLayout(grid, 1)
        logging.info("DashboardPage ctor: header built.")

        # Weather card: value, note and the refresh action live inside the card.
        weather_card = self._make_card_frame(grid, 0, 0, "Погода")
        weather_top_row = QHBoxLayout()
        weather_top_row.setSpacing(8)
        weather_icon = QLabel("…")
        weather_icon.setObjectName("weatherIcon")
        weather_icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        weather_top_row.addWidget(weather_icon)
        weather_value = QLabel("—")
        weather_value.setObjectName("weatherTemperature")
        weather_top_row.addWidget(weather_value)
        weather_top_row.addStretch(1)
        weather_card.layout().addLayout(weather_top_row)
        weather_condition = QLabel(f"Загружаю погоду для {city}…")
        weather_condition.setObjectName("weatherCondition")
        weather_condition.setWordWrap(True)
        weather_card.layout().addWidget(weather_condition)
        weather_forecast = QLabel("")
        weather_forecast.setObjectName("weatherForecast")
        weather_forecast.setWordWrap(True)
        weather_card.layout().addWidget(weather_forecast)
        weather_note = QLabel("")
        weather_note.setObjectName("dashboardCardNote")
        weather_note.setWordWrap(True)
        weather_card.layout().addWidget(weather_note)
        self._weather_text = weather_condition
        self._weather_note = weather_note
        self._weather_icon = weather_icon
        self._weather_temperature = weather_value
        self._weather_forecast = weather_forecast

        city_row = QHBoxLayout()
        city_row.setSpacing(6)
        self._city_edit = QLineEdit(city)
        self._city_edit.setObjectName("weatherCityEdit")
        self._city_edit.setToolTip("Город для прогноза")
        city_row.addWidget(self._city_edit, 1)
        apply_city_button = QPushButton("Применить")
        apply_city_button.setObjectName("secondaryButton")
        apply_city_button.setToolTip("Сохранить город и запросить погоду заново")
        apply_city_button.clicked.connect(self._apply_city_from_editor)
        city_row.addWidget(apply_city_button)
        weather_card.layout().addLayout(city_row)

        refresh_weather_button = QPushButton()
        refresh_weather_button.setIcon(refresh_icon())
        refresh_weather_button.setObjectName("cardIconButton")
        refresh_weather_button.setToolTip("Запросить погоду ещё раз")
        refresh_weather_button.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_weather_button.setFixedSize(24, 24)
        refresh_weather_button.clicked.connect(self._start_weather_fetch)
        card_layout = weather_card.layout()
        title_item = card_layout.takeAt(0)
        title_widget = title_item.widget() if title_item is not None else None
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        if title_widget is not None:
            title_row.addWidget(title_widget)
        else:
            title_row.addWidget(QLabel("Погода"))
        title_row.addStretch(1)
        title_row.addWidget(refresh_weather_button)
        card_layout.insertLayout(0, title_row)
        logging.info("DashboardPage ctor: weather card done.")

        self._make_reminders_card(grid, 0, 1, "Напоминания")
        logging.info("DashboardPage ctor: reminders card built.")
        self.refresh_reminders()
        logging.info("DashboardPage ctor: reminders refreshed.")

        # System card: version + the privacy line — the product's core promise.
        system_card = self._make_card_frame(grid, 1, 0, "Система")
        system_value = QLabel(f"Версия {version or '-'}")
        system_value.setObjectName("dashboardCardValue")
        system_card.layout().addWidget(system_value)
        privacy_label = QLabel("🔒  Всё локально. Ничего не уходит в сеть.")
        privacy_label.setObjectName("privacyNote")
        privacy_label.setWordWrap(True)
        system_card.layout().addWidget(privacy_label)
        logging.info("DashboardPage ctor: system card done.")

        logging.info("DashboardPage ctor: done.")

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

    def _make_reminders_card(self, grid: QGridLayout, row: int, column: int, title: str) -> None:
        card = self._make_card_frame(grid, row, column, title)
        logging.info("DashboardPage ctor: reminders card frame created.")
        self._reminders_list = QListWidget()
        logging.info("DashboardPage ctor: reminders list created.")
        self._reminders_empty = EmptyState(
            "Активных напоминаний нет",
            "Скажи: «напомни в 22:00 проверить чайник» — и я добавлю.",
            glyph="🔔",
        )
        logging.info("DashboardPage ctor: empty state created.")
        self._reminders_stack = QStackedWidget()
        logging.info("DashboardPage ctor: reminders stack created.")
        self._reminders_stack.addWidget(self._reminders_list)
        logging.info("DashboardPage ctor: list added to stack.")
        self._reminders_stack.addWidget(self._reminders_empty)
        logging.info("DashboardPage ctor: empty state added to stack.")
        card.layout().addWidget(self._reminders_stack, 1)
        logging.info("DashboardPage ctor: reminders stack mounted.")

    def refresh_reminders(self) -> None:
        self._reminders_list.clear()
        try:
            entries = self._reminder_store.list_pending()
        except (OSError, ValueError):
            self._reminders_list.addItem("Не удалось загрузить напоминания.")
            self._reminders_stack.setCurrentWidget(self._reminders_list)
            return
        lines = preview_reminders(list(entries))
        if lines:
            for line in lines:
                self._reminders_list.addItem(line)
            self._reminders_stack.setCurrentWidget(self._reminders_list)
        else:
            self._reminders_stack.setCurrentWidget(self._reminders_empty)

    def _start_weather_fetch(self) -> None:
        if self._weather_worker is not None and self._weather_worker.isRunning():
            return
        self._weather_finished = False
        self._weather_text.setText(f"Загружаю погоду для {self._city}…")
        self._weather_note.setText("Обычно это занимает 1–2 секунды.")
        worker = WeatherWorker(self._city)
        worker.setObjectName("weather_worker")
        self._weather_worker = worker

        def on_completed(report: WeatherReport) -> None:
            self._weather_finished = True
            self._weather_text.setText(report.condition.capitalize())
            self._weather_temperature.setText(_temperature_text(report.temperature))
            self._weather_icon.setText(report.icon)
            self._weather_forecast.setText(report.forecast_line())
            detail = []
            if report.apparent is not None:
                detail.append(f"ощущается как {_temperature_text(report.apparent)}")
            if report.wind is not None:
                detail.append(f"ветер {report.wind:.0f} км/ч")
            if report.humidity is not None:
                detail.append(f"влажность {report.humidity:.0f}%")
            self._weather_note.setText(", ".join(detail))

        def on_failed(message: str) -> None:
            self._weather_finished = True
            self._weather_text.setText("Погоду получить не удалось")
            self._weather_temperature.setText("—")
            self._weather_icon.setText("☁️")
            self._weather_forecast.setText("")
            self._weather_note.setText(f"Причина: {message}. Попробуй «Обновить» позже.")

        def on_timeout() -> None:
            if self._weather_finished:
                return
            self._weather_finished = True
            self._weather_text.setText("Погоду получить не удалось")
            self._weather_temperature.setText("—")
            self._weather_icon.setText("☁️")
            self._weather_forecast.setText("")
            self._weather_note.setText(
                "Нет ответа за 15 секунд. Проверь подключение к сети и нажми «Обновить»."
            )

        worker.completed.connect(on_completed)
        worker.failed.connect(on_failed)
        worker.finished.connect(
            lambda: self._weather_workers_clear(worker)
        )
        worker.start()
        QTimer.singleShot(15000, on_timeout)

    def _weather_workers_clear(self, worker: WeatherWorker) -> None:
        if self._weather_worker is worker:
            self._weather_worker = None

    def shutdown(self) -> None:
        """Stop the weather thread; called from app.aboutToQuit."""
        worker = self._weather_worker
        self._weather_worker = None
        if worker is None:
            return
        try:
            if worker.isRunning():
                worker.quit()
                if not worker.wait(2000):
                    worker.terminate()
                    worker.wait(1000)
        except RuntimeError:
            pass

    def _apply_city_from_editor(self) -> None:
        candidate = self._city_edit.text().strip()
        if not candidate:
            return
        if self._on_city_change is not None:
            self._city = self._on_city_change(candidate)
        else:
            self._city = candidate
        self._city_edit.setText(self._city)
        self._weather_fetch_started = False
        self._start_weather_fetch()

    def showEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        if not self._weather_fetch_started:
            self._weather_fetch_started = True
            QTimer.singleShot(300, self._start_weather_fetch)

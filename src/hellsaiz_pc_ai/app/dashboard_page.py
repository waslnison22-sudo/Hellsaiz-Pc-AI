from __future__ import annotations
import logging

from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from hellsaiz_pc_ai.tools.public_info import (
    WeatherCityNotFound,
    WeatherReport,
    get_weather_report,
)

from hellsaiz_pc_ai.app.theme import CARD_SHADOW_BLUR, CARD_SHADOW_OFFSET_Y
from hellsaiz_pc_ai.app.ui_icons import (
    media_back_icon,
    media_next_icon,
    media_pause_icon,
    media_play_icon,
    refresh_icon,
    send_light_icon,
)
from hellsaiz_pc_ai.app.system_metrics import system_snapshot
from hellsaiz_pc_ai.app.ui_fx import reduce_motion as _reduce_motion
from hellsaiz_pc_ai.app.weather_icon import WeatherIconWidget, map_weather_icon
from hellsaiz_pc_ai.app.dashboard_texts import (
    greeting_for_hour,
    greeting_note,
    last_reply_empty_note,
    preview_reminders,
    reminders_count_label,
    system_comment,
)
from hellsaiz_pc_ai.app.hud_components import EmptyState


class WeatherWorker(QThread):
    """Fetches the Open-Meteo report (current, hourly slice, five days)."""

    completed = Signal(object)
    failed = Signal(str)
    city_missing = Signal(str)

    def __init__(self, city: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.city = city

    def run(self) -> None:
        try:
            self.completed.emit(get_weather_report(self.city))
        except WeatherCityNotFound as exc:
            self.city_missing.emit(exc.city)
        except Exception as exc:
            self.failed.emit(str(exc))


def _temperature_text(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = round(value)
    return f"{'+' if rounded > 0 else ''}{rounded}°"


def _forecast_day_html(day: str, temperature: str) -> str:
    """One forecast row: weekday muted, temperature bright — knice style."""
    return (
        f'<span style="color:#A6A29C; font-size:12px;">{day}</span>'
        f'&nbsp;&nbsp;<span style="color:#F2EFEA; font-size:14px; font-weight:600;">{temperature}</span>'
    )


class _ClickableLabel(QLabel):
    """A label acting like a button without losing plain-text rendering."""

    clicked = Signal()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        self.clicked.emit()
        super().mousePressEvent(event)


class DashboardPage(QWidget):
    """Astra-style home hub: weather, media, reminders, quick commands, system."""

    QUICK_COMMANDS = (
        ("Что я умею", "что я умею"),
        ("Погода", "погода"),
        ("Открой блокнот", "открой блокнот"),
        ("Напомни", "напомни в "),
    )
    MEDIA_COMMANDS = {
        "back": "музыка назад",
        "toggle": "музыка пауза",
        "next": "музыка дальше",
    }
    LAST_REPLY_LIMIT = 220

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
        on_open_chat: Callable[[], None] | None = None,
        chat_store: Any = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._reminder_store = reminder_store
        self._city = city
        self._on_send = on_send or (lambda command: None)
        self._on_open_diagnostics = on_open_diagnostics or (lambda: None)
        self._on_city_change = on_city_change
        self._on_open_chat = on_open_chat or (lambda: None)
        self._chat_store = chat_store
        self._assistant_persona = assistant_persona
        self._media_playing = False
        self._weather_fetch_started = False
        self._weather_finished = False
        self._weather_worker: WeatherWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(14)
        logging.info("DashboardPage ctor: entered.")

        self._build_header(layout)

        grid = QGridLayout()
        grid.setSpacing(12)
        # knice hub proportions: narrow sides, a wide centre column.
        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 7)
        grid.setColumnStretch(2, 5)
        layout.addLayout(grid, 1)
        logging.info("DashboardPage ctor: header built.")

        self._build_weather_card(grid)
        self._build_media_card(grid)
        self._build_reminders_card(grid)
        self._build_quick_commands_card(grid)
        self._build_system_card(grid)
        self._build_last_reply_card(grid)
        logging.info("DashboardPage ctor: done.")

        self._metrics_timer = QTimer(self)
        self._metrics_timer.setInterval(3000)
        self._metrics_timer.timeout.connect(self._refresh_metrics)

    # ------------------------------------------------------------------ header

    def _build_header(self, layout: QVBoxLayout) -> None:
        now = datetime.now()
        greeting_label = QLabel(greeting_for_hour(now.hour))
        greeting_label.setObjectName("dashboardGreeting")
        layout.addWidget(greeting_label)
        note_label = QLabel(greeting_note(now.hour, self._assistant_persona))
        note_label.setObjectName("dashboardCardNote")
        layout.addWidget(note_label)
        weekdays_ru = (
            "Понедельник", "Вторник", "Среда", "Четверг",
            "Пятница", "Суббота", "Воскресенье",
        )
        meta_label = QLabel(f"{weekdays_ru[now.weekday()]}, {now:%d.%m.%Y}")
        meta_label.setStyleSheet("color:#A6A29C; font-size:12px;")
        layout.addWidget(meta_label)

    # ------------------------------------------------------------------ shared

    def _make_card_frame(self, grid: QGridLayout, row: int, column: int) -> QFrame:
        card = QFrame()
        card.setObjectName("dashboardCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(8)
        if not _reduce_motion():
            shadow = QGraphicsDropShadowEffect(card)
            shadow.setBlurRadius(CARD_SHADOW_BLUR)
            shadow.setOffset(0, CARD_SHADOW_OFFSET_Y)
            shadow.setColor(QColor(4, 5, 8, 165))
            card.setGraphicsEffect(shadow)
        grid.addWidget(card, row, column)
        return card

    def _title_label(self, title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName("dashboardCardTitle")
        return label

    def _icon_button(
        self, name: str, icon: Any, tooltip: str, size: int = 36
    ) -> QPushButton:
        button = QPushButton()
        button.setIcon(icon)
        button.setObjectName(name)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(size, size)
        return button

    # ------------------------------------------------------------------ weather

    def _build_weather_card(self, grid: QGridLayout) -> None:
        weather_card = self._make_card_frame(grid, 0, 0)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(self._title_label("Погода"))
        title_row.addStretch(1)
        refresh_weather_button = self._icon_button(
            "cardIconButton", refresh_icon(), "Запросить погоду ещё раз", 24
        )
        refresh_weather_button.clicked.connect(self._start_weather_fetch)
        title_row.addWidget(refresh_weather_button)
        weather_card.layout().addLayout(title_row)

        city_stack = QStackedWidget()
        city_stack.setObjectName("cityStack")
        self._city_button = QPushButton(self._city)
        self._city_button.setObjectName("cityButton")
        self._city_button.setToolTip("Кликни, чтобы поменять город")
        self._city_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._city_button.clicked.connect(self._show_city_editor)
        self._city_edit = QLineEdit(self._city)
        self._city_edit.setObjectName("weatherCityEdit")
        self._city_edit.setToolTip("Город для прогноза")
        self._city_edit.returnPressed.connect(self._apply_city_from_editor)
        self._city_edit.installEventFilter(self)
        city_stack.addWidget(self._city_button)
        city_stack.addWidget(self._city_edit)
        city_stack.setCurrentWidget(self._city_button)
        title_row.insertWidget(0, city_stack)

        weather_top_row = QHBoxLayout()
        weather_top_row.setSpacing(8)
        weather_icon = WeatherIconWidget()
        weather_icon.setObjectName("weatherIcon")
        weather_top_row.addWidget(weather_icon, 0, Qt.AlignmentFlag.AlignTop)
        weather_value = QLabel("—")
        weather_value.setObjectName("weatherTemperature")
        weather_top_row.addWidget(weather_value)
        weather_top_row.addStretch(1)
        weather_card.layout().addLayout(weather_top_row)
        self._weather_condition = QLabel(f"Загружаю погоду для {self._city}…")
        self._weather_condition.setObjectName("weatherCondition")
        self._weather_condition.setWordWrap(True)
        weather_card.layout().addWidget(self._weather_condition)
        weather_note = QLabel("")
        weather_note.setObjectName("dashboardCardNote")
        weather_note.setWordWrap(True)
        weather_card.layout().addWidget(weather_note)
        self._weather_note = weather_note
        self._weather_icon = weather_icon
        self._weather_temperature = weather_value

        self._weather_forecast_layout = QVBoxLayout()
        self._weather_forecast_layout.setSpacing(4)
        weather_card.layout().addLayout(self._weather_forecast_layout)
        logging.info("DashboardPage ctor: weather card done.")

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        """Hide the inline city editor on Escape or losing focus."""
        if watched is self._city_edit:
            event_type = event.type()
            if event_type == QEvent.Type.KeyPress and event.key() == Qt.Key_Escape:
                self._hide_city_editor()
                return True
            if event_type == QEvent.Type.FocusOut:
                self._hide_city_editor()
                return True
        return super().eventFilter(watched, event)

    def _show_city_editor(self) -> None:
        self._city_edit.setText(self._city)
        stack = self._city_button.parent()
        if isinstance(stack, QStackedWidget):
            stack.setCurrentWidget(self._city_edit)
            self._city_edit.setFocus()
            self._city_edit.selectAll()

    def _hide_city_editor(self) -> None:
        stack = self._city_edit.parent()
        if isinstance(stack, QStackedWidget):
            stack.setCurrentWidget(self._city_button)

    def _apply_city_from_editor(self) -> None:
        candidate = self._city_edit.text().strip()
        if not candidate:
            self._hide_city_editor()
            return
        if self._on_city_change is not None:
            self._city = self._on_city_change(candidate)
        else:
            self._city = candidate
        self._city_button.setText(self._city)
        self._hide_city_editor()
        self._weather_fetch_started = False
        self._start_weather_fetch()

    # ------------------------------------------------------------------ media

    def _build_media_card(self, grid: QGridLayout) -> None:
        media_card = self._make_card_frame(grid, 1, 0)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(self._title_label("Музыка"))
        title_row.addStretch(1)
        media_card.layout().addLayout(title_row)

        note = QLabel("Управление воспроизведением Windows")
        note.setObjectName("dashboardCardNote")
        note.setWordWrap(True)
        media_card.layout().addWidget(note)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)
        back_button = self._icon_button("mediaButton", media_back_icon(), "Предыдущий трек")
        back_button.clicked.connect(lambda: self._send_media_command("back"))
        controls_row.addWidget(back_button)
        self._media_play_button = self._icon_button(
            "mediaButton", media_play_icon(), "Воспроизвести или поставить на паузу"
        )
        self._media_play_button.clicked.connect(self._toggle_media)
        controls_row.addWidget(self._media_play_button)
        next_button = self._icon_button("mediaButton", media_next_icon(), "Следующий трек")
        next_button.clicked.connect(lambda: self._send_media_command("next"))
        controls_row.addWidget(next_button)
        controls_row.addStretch(1)
        media_card.layout().addLayout(controls_row)
        media_card.layout().addStretch(1)
        logging.info("DashboardPage ctor: media card done.")

    def _send_media_command(self, action: str) -> None:
        self._on_send(self.MEDIA_COMMANDS.get(action, self.MEDIA_COMMANDS["toggle"]))

    def _toggle_media(self) -> None:
        self._media_playing = not self._media_playing
        icon = media_pause_icon() if self._media_playing else media_play_icon()
        self._media_play_button.setIcon(icon)
        self._send_media_command("toggle")

    # ------------------------------------------------------------------ reminders

    def _build_reminders_card(self, grid: QGridLayout) -> None:
        card = self._make_card_frame(grid, 0, 1)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(self._title_label("Напоминания"))
        title_row.addStretch(1)
        self._reminders_count = QLabel("")
        self._reminders_count.setObjectName("remindersCount")
        title_row.addWidget(self._reminders_count)
        card.layout().addLayout(title_row)

        logging.info("DashboardPage ctor: reminders card frame created.")
        self._reminders_list = QListWidget()
        self._reminders_list.setObjectName("dashboardRemindersList")
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
            entries = list(self._reminder_store.list_pending())
        except (OSError, ValueError):
            self._reminders_list.addItem("Не удалось загрузить напоминания.")
            self._reminders_stack.setCurrentWidget(self._reminders_list)
            return
        self._reminders_count.setText(reminders_count_label(len(entries)))
        lines = preview_reminders(entries)
        if lines:
            for line in lines:
                self._reminders_list.addItem(line)
            self._reminders_stack.setCurrentWidget(self._reminders_list)
        else:
            self._reminders_stack.setCurrentWidget(self._reminders_empty)

    # ------------------------------------------------------------------ quick commands

    def _build_quick_commands_card(self, grid: QGridLayout) -> None:
        card = self._make_card_frame(grid, 1, 1)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(self._title_label("Быстрые команды"))
        title_row.addStretch(1)
        card.layout().addLayout(title_row)

        capsule_row = QHBoxLayout()
        capsule_row.setSpacing(8)
        self._quick_input = QLineEdit()
        self._quick_input.setObjectName("quickCommandInput")
        self._quick_input.setPlaceholderText("Спросить Hellsaiz…")
        self._quick_input.returnPressed.connect(self._send_quick_command)
        capsule_row.addWidget(self._quick_input, 1)
        send_button = self._icon_button("mediaButton", send_light_icon(), "Отправить в чат")
        send_button.clicked.connect(self._send_quick_command)
        capsule_row.addWidget(send_button)
        card.layout().addLayout(capsule_row)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        for label, command in self.QUICK_COMMANDS:
            chip = QToolButton()
            chip.setObjectName("quickChip")
            chip.setText(label)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _checked=False, cmd=command: self._use_quick_chip(cmd))
            chips_row.addWidget(chip)
        chips_row.addStretch(1)
        card.layout().addLayout(chips_row)
        card.layout().addStretch(1)
        logging.info("DashboardPage ctor: quick commands card done.")

    def _use_quick_chip(self, command: str) -> None:
        self._quick_input.setText(command)
        self._quick_input.setFocus()
        self._quick_input.setCursorPosition(len(command))

    def _send_quick_command(self) -> None:
        command = self._quick_input.text().strip()
        if not command:
            return
        self._quick_input.clear()
        self._on_send(command)
        self._on_open_chat()

    # ------------------------------------------------------------------ system

    def _build_system_card(self, grid: QGridLayout) -> None:
        card = self._make_card_frame(grid, 0, 2)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(self._title_label("Система"))
        title_row.addStretch(1)
        card.layout().addLayout(title_row)

        self._system_rows: dict[str, dict[str, Any]] = {}
        self._system_bars_layout = QVBoxLayout()
        self._system_bars_layout.setSpacing(6)
        for name in ("CPU", "RAM", "GPU"):
            row = QHBoxLayout()
            row.setSpacing(8)
            label = QLabel(name)
            label.setStyleSheet("color:#A6A29C; font-size:12px;")
            row.addWidget(label, 0, Qt.AlignmentFlag.AlignLeft)
            bar = QProgressBar()
            bar.setObjectName("systemBar")
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            row.addWidget(bar, 1)
            value = QLabel("—")
            value.setObjectName("systemBarValue")
            row.addWidget(value, 0, Qt.AlignmentFlag.AlignRight)
            self._system_bars_layout.addLayout(row)
            self._system_rows[name] = {
                "widgets": (label, bar, value),
                "bar": bar,
                "value": value,
            }
        card.layout().addLayout(self._system_bars_layout)
        self._system_comment = QLabel(system_comment(None))
        self._system_comment.setObjectName("dashboardCardNote")
        self._system_comment.setWordWrap(True)
        card.layout().addWidget(self._system_comment)
        logging.info("DashboardPage ctor: system card done.")

    def _refresh_metrics(self) -> None:
        cpu, ram, gpu = system_snapshot()
        for name, value in (("CPU", cpu), ("RAM", ram), ("GPU", gpu)):
            row = self._system_rows.get(name)
            if row is None:
                continue
            for widget in row["widgets"]:
                widget.setVisible(value is not None)
            if value is None:
                continue
            row["bar"].setValue(int(round(value)))
            row["value"].setText(f"{int(round(value))}%")
        self._system_comment.setText(system_comment(cpu))

    # ------------------------------------------------------------------ last reply

    def _build_last_reply_card(self, grid: QGridLayout) -> None:
        card = self._make_card_frame(grid, 1, 2)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(self._title_label("Последний ответ"))
        title_row.addStretch(1)
        card.layout().addLayout(title_row)

        self._last_reply_text = _ClickableLabel(last_reply_empty_note())
        self._last_reply_text.setObjectName("lastReplyText")
        self._last_reply_text.setWordWrap(True)
        self._last_reply_text.setCursor(Qt.CursorShape.PointingHandCursor)
        self._last_reply_text.clicked.connect(self._on_open_chat)
        card.layout().addWidget(self._last_reply_text)
        self._last_reply_time = QLabel("")
        self._last_reply_time.setObjectName("lastReplyTime")
        card.layout().addWidget(self._last_reply_time)
        card.layout().addStretch(1)
        logging.info("DashboardPage ctor: last reply card done.")

    def set_last_reply(self, text: str, when: datetime | None = None) -> None:
        """Called from the desktop shell whenever the assistant answers."""
        clean = " ".join((text or "").split())
        if clean:
            if len(clean) > self.LAST_REPLY_LIMIT:
                clean = clean[: self.LAST_REPLY_LIMIT].rstrip() + "…"
            self._last_reply_text.setText(clean)
            self._last_reply_time.setText(
                (when or datetime.now()).strftime("%H:%M")
            )
            self._last_reply_text.setEnabled(True)
        else:
            self._last_reply_text.setText(last_reply_empty_note())
            self._last_reply_time.setText("")

    # ------------------------------------------------------------------ weather worker

    def _start_weather_fetch(self) -> None:
        if self._weather_worker is not None and self._weather_worker.isRunning():
            return
        self._weather_finished = False
        self._weather_condition.setText(f"Загружаю погоду для {self._city}…")
        self._weather_note.setText("Обычно это занимает 1–2 секунды.")
        worker = WeatherWorker(self._city)
        worker.setObjectName("weather_worker")
        self._weather_worker = worker

        def on_completed(report: WeatherReport) -> None:
            self._weather_finished = True
            self._weather_condition.setText(report.condition.capitalize())
            self._weather_icon.set_dimmed(False)
            self._weather_icon.set_icon(
                map_weather_icon(report.condition, datetime.now().hour)
            )
            self._weather_temperature.setText(_temperature_text(report.temperature))
            self._weather_note.setText(
                ", ".join(self._weather_details(report))
            )
            self._rebuild_forecast(report)

        def on_failed(message: str) -> None:
            # The technical reason stays in the log; the card shows a human hint.
            logging.warning("Weather fetch failed: %s", message)
            self._weather_finished = True
            self._weather_condition.setText("Погоду получить не удалось")
            self._weather_temperature.setText("—")
            self._weather_icon.set_dimmed(True)
            self._clear_forecast()
            self._weather_note.setText(
                "Не получилось связаться с сервисом погоды — проверь интернет и попробуй позже."
            )

        def on_timeout() -> None:
            if self._weather_finished:
                return
            self._weather_finished = True
            self._weather_condition.setText("Погоду получить не удалось")
            self._weather_temperature.setText("—")
            self._weather_icon.set_dimmed(True)
            self._clear_forecast()
            self._weather_note.setText(
                "Нет ответа за 15 секунд. Проверь подключение к сети и нажми «Обновить».")

        def on_city_missing(city: str) -> None:
            self._weather_finished = True
            self._weather_condition.setText("Погоду получить не удалось")
            self._weather_temperature.setText("—")
            self._weather_icon.set_dimmed(True)
            self._clear_forecast()
            self._weather_note.setText(
                f"Города «{city}» нет в базе сервиса — проверь название."
            )

        worker.completed.connect(on_completed)
        worker.failed.connect(on_failed)
        worker.city_missing.connect(on_city_missing)
        worker.finished.connect(
            lambda: self._weather_workers_clear(worker)
        )
        worker.start()
        QTimer.singleShot(15000, on_timeout)

    @staticmethod
    def _weather_details(report: WeatherReport) -> list[str]:
        detail: list[str] = []
        if report.apparent is not None:
            detail.append(f"ощущается как {_temperature_text(report.apparent)}")
        if report.wind is not None:
            detail.append(f"ветер {report.wind:.0f} км/ч")
        if report.humidity is not None:
            detail.append(f"влажность {report.humidity:.0f}%")
        return detail

    def _clear_forecast(self) -> None:
        while self._weather_forecast_layout.count():
            item = self._weather_forecast_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_forecast(self, report: WeatherReport) -> None:
        self._clear_forecast()
        for day, temperature in report.forecast_items():
            label = QLabel(_forecast_day_html(day, temperature))
            self._weather_forecast_layout.addWidget(label)

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

    def showEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        if not self._weather_fetch_started:
            self._weather_fetch_started = True
            QTimer.singleShot(300, self._start_weather_fetch)
        if not self._metrics_timer.isActive():
            self._refresh_metrics()
            self._metrics_timer.start()

    def hideEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        super().hideEvent(event)
        if self._metrics_timer.isActive():
            self._metrics_timer.stop()

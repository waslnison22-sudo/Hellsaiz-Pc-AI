from __future__ import annotations
import logging
import math
import re

from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import (
    QObject,
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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

from hellsaiz_pc_ai.app.theme import (
    ACCENT_SOLID,
    DASHBOARD_SURFACE,
    CARD_PADDING,
    DASHBOARD_MARGIN_BOTTOM,
    DASHBOARD_MARGIN_SIDE,
    DASHBOARD_MARGIN_TOP,
    GRID_BREAKPOINTS,
    GRID_GAP,
    TEXT_MUTED,
)
from hellsaiz_pc_ai.app.icons import load_icon
from hellsaiz_pc_ai.app.ui_icons import (
    media_back_icon,
    media_next_icon,
    media_pause_icon,
    media_play_icon,
    refresh_icon,
    send_light_icon,
)
from hellsaiz_pc_ai.app.system_metrics import system_snapshot
from hellsaiz_pc_ai.app.weather_cache import (
    load_weather_cache,
    save_weather_cache,
    updated_label,
)
from hellsaiz_pc_ai.app.ui_fx import reduce_motion as _reduce_motion
from hellsaiz_pc_ai.app.yandex_music import (
    media_session,
    now_playing,
    open_or_focus_player,
)
from hellsaiz_pc_ai.app.weather_icon import WeatherIconWidget, map_weather_icon
from hellsaiz_pc_ai.app.dashboard_texts import (
    greeting_for_hour,
    greeting_note,
    last_reply_empty_note,
    system_comment,
)


def columns_for_width(width: int) -> int:
    """Adaptive grid: 1 column on narrow windows, 2 standard, 3 on wide ones."""
    for threshold, columns in GRID_BREAKPOINTS:
        if width <= threshold:
            return columns
    return GRID_BREAKPOINTS[-1][1]


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


def _forecast_chip(day: str, temperature: str) -> QLabel:
    """One compact forecast chip: «Пт +5°» in a pill."""
    chip = QLabel(f"{day}  {temperature}")
    chip.setObjectName("weatherForecastChip")
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return chip


class _ShadowCard(QFrame):
    """Card that paints its own soft shadow inside the widget.

    A QGraphicsDropShadowEffect is clipped by the parent and disappears when an
    ancestor (the page fader) also uses a graphics effect, so the knice shadow is
    drawn in paintEvent with an internal shadow margin instead.
    """

    RADIUS = 22
    SHADOW_MARGIN = 10

    def paintEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inner = QRectF(self.rect()).adjusted(
            self.SHADOW_MARGIN,
            self.SHADOW_MARGIN / 2,
            -self.SHADOW_MARGIN,
            -self.SHADOW_MARGIN,
        )
        for step, alpha in ((6.0, 16), (4.0, 24), (2.0, 32)):
            path = QPainterPath()
            path.addRoundedRect(
                inner.adjusted(-step, -step / 2, step, step * 1.6),
                self.RADIUS + step,
                self.RADIUS + step,
            )
            painter.fillPath(path, QColor(4, 5, 8, alpha))
        surface = QPainterPath()
        surface.addRoundedRect(inner, self.RADIUS, self.RADIUS)
        painter.fillPath(surface, QColor(33, 34, 38))
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1.0))
        painter.drawLine(
            QPointF(inner.left() + self.RADIUS, inner.top() + 0.5),
            QPointF(inner.right() - self.RADIUS, inner.top() + 0.5),
        )
        painter.end()


class _ClickableLabel(QLabel):
    """A label acting like a button without losing plain-text rendering."""

    clicked = Signal()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        self.clicked.emit()
        super().mousePressEvent(event)


class MediaPollThread(QThread):
    """Polls the Windows media session off the GUI thread."""

    session_ready = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def run(self) -> None:  # noqa: D102 - QThread entry point
        while not self._stopped:
            try:
                session = media_session()
            except Exception:  # noqa: BLE001 - polling must never kill the thread
                logging.debug("Media poll failed", exc_info=True)
                session = None
            if self._stopped:
                break
            self.session_ready.emit(session)
            self.msleep(2500)


class PulseCover(QWidget):
    """Album art with a soft beat pulse in the cover's dominant colour.

    The halo is painted inside the widget margins, so the card background never
    changes: only the plate around the artwork pulses.
    """

    SIZE = 104
    ART = 76

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mediaCoverPulse")
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Открыть Яндекс Музыку")
        self._art = QPixmap()
        self._color = QColor(ACCENT_SOLID)
        self._phase = 0.0
        self._playing = False

    # -- data ---------------------------------------------------------------
    def set_artwork(self, artwork: bytes) -> None:
        pixmap = QPixmap()
        if not artwork or not pixmap.loadFromData(artwork):
            self._art = QPixmap()
            self._color = QColor(ACCENT_SOLID)
            self.update()
            return
        scaled = pixmap.scaled(
            self.ART,
            self.ART,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QPixmap(self.ART, self.ART)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.ART, self.ART, 18, 18)
        painter.setClipPath(path)
        painter.drawPixmap(
            (self.ART - scaled.width()) // 2,
            (self.ART - scaled.height()) // 2,
            scaled,
        )
        painter.end()
        self._art = canvas
        self._color = self._dominant_colour(pixmap)
        self.update()

    @staticmethod
    def _dominant_colour(pixmap: QPixmap) -> QColor:
        image = pixmap.toImage().scaled(
            1, 1, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return QColor(image.pixel(0, 0))

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        if not playing:
            self._phase = 0.0
        self.update()

    def advance(self) -> None:
        if not self._playing:
            return
        self._phase = (self._phase + 0.16) % 6.28318
        self.update()

    # -- painting -----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        offset = (self.SIZE - self.ART) // 2
        if self._playing:
            pulse = (math.sin(self._phase) + 1.0) / 2.0
            for index, alpha in ((0, 70), (1, 40), (2, 22)):
                inset = offset - 6 - index * 5 - pulse * 4
                halo = QColor(self._color)
                halo.setAlpha(int(alpha * (0.55 + 0.45 * pulse)))
                painter.setBrush(halo)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(
                    int(inset), int(inset),
                    int(self.SIZE - inset * 2), int(self.SIZE - inset * 2),
                    22, 22,
                )
        if not self._art.isNull():
            painter.drawPixmap(offset, offset, self._art)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(DASHBOARD_SURFACE))
            painter.drawRoundedRect(offset, offset, self.ART, self.ART, 18, 18)
            icon = media_play_icon().pixmap(30, 30)
            painter.drawPixmap(
                offset + (self.ART - 30) // 2, offset + (self.ART - 30) // 2, icon
            )
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class DashboardPage(QWidget):
    """Astra-style home hub: weather, media, reminders, quick commands, system."""

    QUICK_COMMANDS = (
        ("Что я умею", "что я умею", "sparkles"),
        ("Погода", "погода", "globe"),
        ("Открой блокнот", "открой блокнот", "house"),
        ("Напомни", "напомни в ", "bell"),
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
        layout.setContentsMargins(
            DASHBOARD_MARGIN_SIDE,
            DASHBOARD_MARGIN_TOP,
            DASHBOARD_MARGIN_SIDE,
            DASHBOARD_MARGIN_BOTTOM,
        )
        layout.setSpacing(GRID_GAP)
        logging.info("DashboardPage ctor: entered.")

        self._cards: list[QFrame] = []
        self._columns = 0

        self._build_header(layout)

        self._grid = QGridLayout()
        self._grid.setSpacing(GRID_GAP)
        self._grid.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._grid, 1)
        logging.info("DashboardPage ctor: header built.")

        self._build_weather_card()
        self._build_media_card()
        self._build_quick_commands_card()
        self._build_system_card()
        self._build_last_reply_card()
        self._relayout_grid(self.width(), force=True)
        logging.info("DashboardPage ctor: done.")

        self._metrics_timer = QTimer(self)
        self._metrics_timer.setInterval(3000)
        self._metrics_timer.timeout.connect(self._refresh_metrics)

    # ------------------------------------------------------------------ header

    def _build_header(self, layout: QVBoxLayout) -> None:
        now = datetime.now()
        from hellsaiz_pc_ai.app.chat_page import GradientBrandLabel

        greeting_label = GradientBrandLabel(
            f"{greeting_for_hour(now.hour)}, Хеллсайз",
            40,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        greeting_label.setMinimumHeight(58)
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
        meta_label.setStyleSheet(f"color:{TEXT_MUTED}; font-size:12px;")
        layout.addWidget(meta_label)

    # ------------------------------------------------------------------ shared

    def _make_card_frame(self) -> QFrame:
        card = _ShadowCard()
        card.setObjectName("dashboardCard")
        margin = _ShadowCard.SHADOW_MARGIN
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(
            CARD_PADDING + margin,
            CARD_PADDING + margin // 2,
            CARD_PADDING + margin,
            CARD_PADDING + margin,
        )
        card_layout.setSpacing(8)
        self._cards.append(card)
        return card

    def _relayout_grid(self, width: int, *, force: bool = False) -> None:
        """Re-flow the cards into 1/2/3 columns; shadows keep their margins.

        Rows are sized by the cards themselves: stretching every row made tall
        cards overlap their own children (the big temperature sat on top of the
        condition line), so the spare vertical space goes to a trailing spacer
        row instead.
        """
        columns = columns_for_width(int(width))
        if not force and columns == self._columns:
            return
        self._columns = columns
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self)
        for index, card in enumerate(self._cards):
            self._grid.addWidget(card, index // columns, index % columns)
        for column in range(3):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)
        card_rows = (len(self._cards) + columns - 1) // columns
        # Stretches from the previous column count must be cleared, otherwise the
        # leftover stretched rows push the cards to the top of the page.
        for row in range(12):
            self._grid.setRowStretch(row, 0)
        for row in range(card_rows):
            self._grid.setRowStretch(row, 1)
        # A short last row stretches its cards so the grid has no holes.
        remainder = len(self._cards) % columns
        if self._cards and 0 < remainder < columns:
            extra = columns - remainder
            self._grid.addWidget(
                self._cards[-1], card_rows - 1, remainder - 1, 1, extra + 1
            )

    def resizeEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._relayout_grid(self.width())

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

    def _build_weather_card(self) -> None:
        weather_card = self._make_card_frame()

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
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
        # The generic QPushButton fill painted a black box behind the city name;
        # a widget-level rule wins over the app stylesheet.
        self._city_button.setStyleSheet(
            "background: transparent; border: 0; padding: 0;"
        )
        self._city_button.setMinimumHeight(0)
        self._city_edit = QLineEdit(self._city)
        self._city_edit.setObjectName("weatherCityEdit")
        self._city_edit.setToolTip("Город для прогноза")
        self._city_edit.returnPressed.connect(self._apply_city_from_editor)
        self._city_edit.installEventFilter(self)
        city_stack.setStyleSheet("background: transparent;")
        city_stack.addWidget(self._city_button)
        city_stack.addWidget(self._city_edit)
        city_stack.setCurrentWidget(self._city_button)
        # «Погода · Ставрополь»: the city lives on its own line, never glued to
        # the card title.
        city_row = QHBoxLayout()
        city_row.setSpacing(0)
        city_row.addWidget(city_stack)
        city_row.addStretch(1)
        weather_card.layout().addLayout(city_row)

        weather_top_row = QHBoxLayout()
        weather_top_row.setSpacing(12)
        weather_icon = WeatherIconWidget(size=58)
        # Pin the glyph size: the card layout used to squeeze it to half.
        weather_icon.setFixedSize(58, 58)
        weather_icon.setObjectName("weatherIcon")
        weather_top_row.addWidget(weather_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        weather_value = QLabel("—")
        weather_value.setObjectName("weatherTemperature")
        weather_value.setMinimumWidth(120)
        weather_value.setFixedHeight(56)
        weather_value.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        # The number gets its own card row: inside the icon row a squeezed card
        # overlapped the details line with the glyphs.
        weather_card.layout().addWidget(weather_value)
        # The condition sits beside the number in the same row: a squeezed card
        # can never stack the caption on top of the temperature glyphs.
        self._weather_condition = QLabel(f"Загружаю погоду для {self._city}…")
        self._weather_condition.setObjectName("weatherCondition")
        self._weather_condition.setWordWrap(True)
        self._weather_condition.setMinimumWidth(160)
        weather_top_row.addWidget(
            self._weather_condition, 1, Qt.AlignmentFlag.AlignBottom
        )
        weather_card.layout().addLayout(weather_top_row)

        weather_note = QLabel("")
        weather_note.setObjectName("dashboardCardNote")
        weather_note.setWordWrap(True)
        weather_note.setMinimumHeight(20)
        weather_card.layout().addWidget(weather_note)
        self._weather_note = weather_note
        self._weather_card = weather_card
        weather_updated = QLabel("")
        weather_updated.setObjectName("dashboardCardNote")
        weather_card.layout().addWidget(weather_updated)
        self._weather_updated = weather_updated
        self._weather_icon = weather_icon
        self._weather_temperature = weather_value

        self._weather_forecast_layout = QHBoxLayout()
        self._weather_forecast_layout.setSpacing(8)
        weather_card.layout().addLayout(self._weather_forecast_layout)
        logging.info("DashboardPage ctor: weather card done.")

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        """Hide the inline city editor on Escape, clear the quick input on Escape."""
        if watched is getattr(self, "_quick_input", None):
            if (
                event.type() == QEvent.Type.KeyPress
                and event.key() == Qt.Key_Escape
            ):
                self._quick_input.clear()
                return True
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

    def _build_media_card(self) -> None:
        media_card = self._make_card_frame()

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(self._title_label("Музыка"))
        title_row.addStretch(1)
        self._player_state = QLabel("")
        self._player_state.setObjectName("mediaState")
        title_row.addWidget(self._player_state)
        media_card.layout().addLayout(title_row)

        cover_row = QHBoxLayout()
        cover_row.setSpacing(14)
        self._media_cover = PulseCover()
        self._media_cover.clicked.connect(self._open_player)
        cover_row.addWidget(self._media_cover, 0, Qt.AlignmentFlag.AlignVCenter)
        cover_column = QVBoxLayout()
        cover_column.setSpacing(3)
        self._media_track = QLabel("Яндекс Музыка не запущена")
        self._media_track.setObjectName("mediaTrack")
        self._media_track.setWordWrap(True)
        cover_column.addWidget(self._media_track)
        self._media_artist = QLabel("Нажми на обложку — открою плеер")
        self._media_artist.setObjectName("mediaArtist")
        self._media_artist.setWordWrap(True)
        cover_column.addWidget(self._media_artist)
        cover_column.addStretch(1)
        cover_row.addLayout(cover_column, 1)
        media_card.layout().addLayout(cover_row)
        media_card.layout().addStretch(1)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)
        self._media_back_button = self._icon_button(
            "mediaButton", media_back_icon(), "Предыдущий трек"
        )
        self._media_back_button.clicked.connect(lambda: self._send_media_command("back"))
        controls_row.addWidget(self._media_back_button)
        self._media_play_button = self._icon_button(
            "mediaButton", media_play_icon(), "Играть или пауза"
        )
        self._media_play_button.clicked.connect(self._toggle_media)
        controls_row.addWidget(self._media_play_button)
        self._media_next_button = self._icon_button(
            "mediaButton", media_next_icon(), "Следующий трек"
        )
        self._media_next_button.clicked.connect(lambda: self._send_media_command("next"))
        controls_row.addWidget(self._media_next_button)
        controls_row.addStretch(1)
        for button in (
            self._media_back_button,
            self._media_play_button,
            self._media_next_button,
        ):
            button.setFixedSize(46, 46)
        media_card.layout().addLayout(controls_row)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(60)
        self._pulse_timer.timeout.connect(self._advance_pulse)

        self._player_timer = QTimer(self)
        self._player_timer.setInterval(2000)
        self._player_timer.timeout.connect(self._refresh_now_playing)
        logging.info("DashboardPage ctor: media card done.")

    def _advance_pulse(self) -> None:
        cover = getattr(self, "_media_cover", None)
        if cover is not None:
            cover.advance()

    def _set_pulse_playing(self, playing: bool) -> None:
        cover = getattr(self, "_media_cover", None)
        if cover is not None:
            cover.set_playing(playing)
        timer = getattr(self, "_pulse_timer", None)
        if timer is None:
            return
        if playing and not timer.isActive():
            timer.start()
        elif not playing and timer.isActive():
            timer.stop()

    def _set_cover(self, artwork: bytes, has_track: bool) -> None:
        """Compatibility shim: the pulse plate owns the artwork now."""
        cover = getattr(self, "_media_cover", None)
        if cover is None:
            return
        if artwork:
            cover.set_artwork(artwork)
        elif not has_track:
            cover.set_artwork(b"")

    def _refresh_now_playing(self) -> None:
        """Cheap, non-blocking fallback: the Yandex Music window title."""
        if not hasattr(self, "_media_track"):
            return
        try:
            playing = now_playing()
        except Exception:  # noqa: BLE001 - the player probe must never break the page
            logging.debug("Now playing probe failed", exc_info=True)
            playing = None
        if playing is None or not playing.has_track:
            self._media_track.setText("Яндекс Музыка не запущена")
            self._media_artist.setText("Нажми «Открыть» — карточка подхватит трек")
            self._player_state.setText("")
            self._set_cover(b"", False)
            for button in (
                self._media_back_button,
                self._media_play_button,
                self._media_next_button,
            ):
                button.setEnabled(False)
            return
        for button in (
            self._media_back_button,
            self._media_play_button,
            self._media_next_button,
        ):
            button.setEnabled(True)
        self._media_track.setText(playing.display_line())
        self._media_artist.setText("Яндекс Музыка · системные медиа-клавиши")
        self._player_state.setText(
            "играет" if getattr(self, "_media_playing", False) else "пауза"
        )

    def _open_player(self) -> None:
        result = open_or_focus_player()
        if result == "focused":
            self._player_state.setText("окно открыто")
            return
        if result == "launched":
            self._player_state.setText("запускаю")
            self._media_track.setText("Открываю Яндекс Музыку…")
            self._media_artist.setText("Трек появится через секунду")
            QTimer.singleShot(4000, self._refresh_now_playing)
            return
        self._media_track.setText("Яндекс Музыка не найдена")
        self._media_artist.setText(
            "Установи приложение «Яндекс Музыка» — карточка подхватит трек"
        )

    def _ensure_media_thread(self) -> None:
        thread = getattr(self, "_media_thread", None)
        if thread is not None and thread.isRunning():
            return
        self._media_thread = MediaPollThread(self)
        self._media_thread.session_ready.connect(self._apply_media_session)
        self._media_thread.start()

    def _stop_media_thread(self) -> None:
        thread = getattr(self, "_media_thread", None)
        if thread is None:
            return
        thread.stop()
        thread.wait(3000)
        self._media_thread = None

    GENERIC_TITLES = ("яндекс музыка", "собираю музыку", "yandex music", "реклама")

    SERVICE_TITLE_RE = re.compile(r"собира\w*\s+музыку|яндекс\s*музык|yandex\s*music|реклама")

    @classmethod
    def _is_meaningful(cls, session: object) -> bool:
        """Ignore service titles (app name, radio promos) so the track never flickers."""
        title = str(getattr(session, "title", "") or "").strip().casefold()
        if not title or title in cls.GENERIC_TITLES:
            return False
        if cls.SERVICE_TITLE_RE.search(title):
            return False
        return getattr(session, "has_track", False)

    def _apply_media_session(self, session: object) -> None:
        """Update the player card from a session snapshot (no blocking IO).

        A single empty probe (pause, app switch, COM hiccup) must not wipe the
        card: the last track stays until several consecutive misses.
        """
        if session is not None and self._is_meaningful(session):
            self._media_misses = 0
            for button in (
                self._media_back_button,
                self._media_play_button,
                self._media_next_button,
            ):
                button.setEnabled(True)
            self._media_track.setText(session.display_line())
            source = "Яндекс Музыка" if "yandex" in session.app.casefold() else session.app
            self._media_artist.setText(f"{source} · {session.status}")
            self._player_state.setText(session.status)
            artwork = getattr(session, "artwork", b"")
            if artwork:
                self._media_cover.set_artwork(artwork)
            self._media_playing = session.status == "играет"
            self._set_pulse_playing(self._media_playing)
            icon = media_pause_icon() if self._media_playing else media_play_icon()
            self._media_play_button.setIcon(icon)
            return
        misses = getattr(self, "_media_misses", 0) + 1
        self._media_misses = misses
        if misses < 8 and getattr(self, "_media_track", None) is not None:
            # Keep the last known track on screen; only update pause/play state.
            if getattr(session, "status", "") in {"пауза", "играет"}:
                self._player_state.setText(session.status)
            return
        self._media_track.setText("Яндекс Музыка не запущена")
        self._media_artist.setText("Нажми на обложку — открою плеер")
        self._player_state.setText("")
        self._set_pulse_playing(False)
        self._media_cover.set_artwork(b"")
        for button in (
            self._media_back_button,
            self._media_play_button,
            self._media_next_button,
        ):
            button.setEnabled(False)

    def _start_player_watch(self) -> None:
        self._refresh_now_playing()
        if not self._player_timer.isActive():
            self._player_timer.start()

    def _stop_player_watch(self) -> None:
        if getattr(self, "_player_timer", None) is not None and self._player_timer.isActive():
            self._player_timer.stop()

    def _send_media_command(self, action: str) -> None:
        self._on_send(self.MEDIA_COMMANDS.get(action, self.MEDIA_COMMANDS["toggle"]))

    def _toggle_media(self) -> None:
        self._media_playing = not self._media_playing
        icon = media_pause_icon() if self._media_playing else media_play_icon()
        self._media_play_button.setIcon(icon)
        self._media_state.setText(
            "Состояние: играет" if self._media_playing else "Состояние: пауза"
        )
        self._send_media_command("toggle")

    # ------------------------------------------------------------------ reminders

    def refresh_reminders(self) -> None:
        """Reminders now live on their own page; kept as a no-op for callers."""
        return

    # ------------------------------------------------------------------ quick commands

    def _build_quick_commands_card(self) -> None:
        card = self._make_card_frame()
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
        self._quick_input.installEventFilter(self)
        capsule_row.addWidget(self._quick_input, 1)
        send_button = self._icon_button("mediaButton", send_light_icon(), "Отправить в чат")
        send_button.clicked.connect(self._send_quick_command)
        capsule_row.addWidget(send_button)
        card.layout().addLayout(capsule_row)

        card.layout().addStretch(1)
        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        for label, command, icon_name in self.QUICK_COMMANDS:
            chip = QToolButton()
            chip.setObjectName("quickChip")
            chip.setText(label)
            chip.setIcon(load_icon(icon_name, ACCENT_SOLID))
            chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _checked=False, cmd=command: self._use_quick_chip(cmd))
            chips_row.addWidget(chip)
        chips_row.addStretch(1)
        card.layout().addLayout(chips_row)
        hint = QLabel("Enter — отправить, Esc — сбросить")
        hint.setObjectName("dashboardCardNote")
        card.layout().addWidget(hint)
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

    def _build_system_card(self) -> None:
        card = self._make_card_frame()
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
            label.setStyleSheet(f"color:{TEXT_MUTED}; font-size:12px;")
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
        card.layout().addStretch(1)
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
            text_value = f"{int(round(value))}%"
            if row["value"].text() != text_value:
                row["value"].setText(text_value)
                self._flash_widget(row["value"])
        self._system_comment.setText(system_comment(cpu))

    # ------------------------------------------------------------------ last reply

    def _build_last_reply_card(self) -> None:
        card = self._make_card_frame()
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
                " · ".join(self._weather_details(report))
            )
            self._rebuild_forecast(report)
            payload = {
                "city": self._city,
                "condition": self._weather_condition.text(),
                "temperature": self._weather_temperature.text(),
                "details": self._weather_note.text(),
            }
            save_weather_cache(payload)
            self._weather_updated.setText(updated_label(load_weather_cache() or payload))
            self._lock_card_minimum(self._weather_card)

        def on_failed(message: str) -> None:
            # The technical reason stays in the log; the card shows a human hint.
            logging.warning("Weather fetch failed: %s", message)
            self._weather_finished = True
            self._apply_cached_weather()

        def on_timeout() -> None:
            if self._weather_finished:
                return
            self._weather_finished = True
            self._apply_cached_weather()

        def on_city_missing(city: str) -> None:
            self._weather_finished = True
            self._weather_condition.setText("город не найден")
            self._weather_temperature.setText("—")
            self._weather_icon.set_dimmed(True)
            self._clear_forecast()
            self._weather_note.setText(f"Города «{city}» нет в базе — проверь название.")
            self._weather_updated.setText("")

        worker.completed.connect(on_completed)
        worker.failed.connect(on_failed)
        worker.city_missing.connect(on_city_missing)
        worker.finished.connect(
            lambda: self._weather_workers_clear(worker)
        )
        worker.start()
        QTimer.singleShot(15000, on_timeout)

    def _apply_cached_weather(self) -> None:
        """Offline state: show the saved report, or a human empty state."""
        cached = load_weather_cache()
        self._clear_forecast()
        if not cached:
            self._weather_condition.setText("нет сети")
            self._weather_temperature.setText("—")
            self._weather_icon.set_dimmed(True)
            self._weather_note.setText("Погода появится, когда появится сеть.")
            self._weather_updated.setText("")
            self._lock_card_minimum(self._weather_card)
            return
        self._weather_condition.setText(str(cached.get("condition") or "нет сети"))
        self._weather_temperature.setText(str(cached.get("temperature") or "—"))
        self._weather_icon.set_dimmed(True)
        self._weather_note.setText("Нет соединения — показаны сохранённые данные")
        self._weather_updated.setText(updated_label(cached))
        self._lock_card_minimum(self._weather_card)

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
        # Three compact chips in a row keep the card short on small screens.
        for day, temperature in report.forecast_items()[:3]:
            self._weather_forecast_layout.addWidget(
                _forecast_chip(day, temperature)
            )
        self._weather_forecast_layout.addStretch(1)

    def _weather_workers_clear(self, worker: WeatherWorker) -> None:
        if self._weather_worker is worker:
            self._weather_worker = None

    def _flash_widget(self, widget: QWidget) -> None:
        """Soft 180 ms opacity pulse on a value change (skipped when motion is off)."""
        if _reduce_motion():
            return
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.35)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(180)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutQuad)

        def finish() -> None:
            try:
                widget.setGraphicsEffect(None)
            except RuntimeError:
                return

        animation.finished.connect(finish)
        widget._flash_animation = animation
        animation.start()

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

    @staticmethod
    def _lock_card_minimum(card: QWidget) -> None:
        """Raise a card's minimum height to what its own layout needs."""
        layout = card.layout()
        if layout is None:
            return
        layout.activate()
        minimum = layout.minimumSize().height()
        if minimum > card.minimumHeight():
            card.setMinimumHeight(minimum)

    def _lock_card_minimums(self) -> None:
        """Cards never shrink below their content, so labels cannot overlap."""
        for card in self._cards:
            self._lock_card_minimum(card)

    def showEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        QTimer.singleShot(0, self._lock_card_minimums)
        if not self._weather_fetch_started:
            self._weather_fetch_started = True
            QTimer.singleShot(300, self._start_weather_fetch)
        if not self._metrics_timer.isActive():
            self._refresh_metrics()
            self._metrics_timer.start()
        self._start_player_watch()
        QTimer.singleShot(2500, self._ensure_media_thread)

    def hideEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        super().hideEvent(event)
        if self._metrics_timer.isActive():
            self._metrics_timer.stop()
        self._stop_player_watch()
        self._set_pulse_playing(False)
        self._stop_media_thread()

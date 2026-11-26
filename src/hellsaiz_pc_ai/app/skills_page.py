"""Page «Что я умею?» — honest capability cards, no invented features.

Every card mirrors real commands from core/commands.py HELP_TEXT.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from hellsaiz_pc_ai.app.icons import load_icon
from hellsaiz_pc_ai.app.ui_fx import install_button_fx

# Icon names come from the vendored Lucide set: emoji glyphs render as tofu on
# machines without an emoji font.
SKILL_CARDS: tuple[tuple[str, str, str], ...] = (
    ("zap", "Программы", "Запуск разрешённых приложений по имени: блокнот, калькулятор, проводник, игры."),
    ("house", "Окна", "«Покажи открытые окна», «переключись на Блокнот», «сверни окно», «заблокируй компьютер»."),
    ("volume-2", "Звук и медиа", "Громкость шагом («громче», «громче на 20»), пауза и треки, «включи музыку дождь»."),
    ("settings", "Сеть и VPN", "«Включи впн», «выключи впн», «проверь впн» — через локальный клиент v2RayTun."),
    ("bell", "Напоминания", "«Напомни через 5 минут…», «напомни в 22:00…», «мои напоминания» — до 30 дней."),
    ("sparkles", "Погода и курсы", "«Погода в Москве», «собираюсь погулять», «курс доллара к рублю»."),
    ("circle-check", "Счёт и поиск", "«Сколько будет 12 умножить на 3», «найди в интернете…», «открой сайт example.com»."),
    ("send", "Файлы и буфер", "«Покажи файлы в папке Документы», «прочитай файл…», «скопируй…», «что в буфере обмена»."),
    ("circle-alert", "Экран и окна-контролы", "«Прочитай текст на экране», «нажми Сохранить в окне Блокнот», «введи текст в поле…»."),
    ("play", "Сценарии", "Своя автоматизация: цепочки действий по расписанию, автозапуску и горячей клавише."),
    ("mic", "Голос", "Wake-слово «Хеллсайз», локальное распознавание речи и озвучка ответов."),
    ("user-round", "Приватность", "Всё локально: никакие команды и разговоры не уходят в сеть. Произвольный код не запускается."),
)


def _skill_card(icon_name: str, title: str, note: str) -> QFrame:
    card = QFrame()
    card.setObjectName("skillCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)
    header = QHBoxLayout()
    header.setSpacing(8)
    icon_label = QLabel()
    icon_label.setObjectName("skillCardIcon")
    icon_label.setFixedSize(20, 20)
    icon_label.setPixmap(load_icon(icon_name, "#E8C29E").pixmap(18, 18))
    header.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)
    title_label = QLabel(title)
    title_label.setObjectName("skillCardTitle")
    title_label.setWordWrap(True)
    header.addWidget(title_label, 1)
    layout.addLayout(header)
    note_label = QLabel(note)
    note_label.setObjectName("skillCardNote")
    note_label.setWordWrap(True)
    layout.addWidget(note_label)
    # Cards are not buttons, but the same hover feedback makes the grid lively.
    install_button_fx(card, base="#161615", hover="#1E1E1C", pressed="#121211")
    return card


class SkillsPage(QWidget):
    """Honest capability overview built from the local command router."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(12)

        greeting = QLabel("Что я умею")
        greeting.setObjectName("dashboardGreeting")
        greeting.setStyleSheet("font-size:26px; font-weight:700; color:#F2EFEA;")
        layout.addWidget(greeting)
        note = QLabel("Полный список возможностей — без воды и лишних слов.")
        note.setStyleSheet("color:#A6A29C; font-size:13px;")
        layout.addWidget(note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll, 1)
        inner = QWidget()
        scroll.setWidget(inner)
        grid = QGridLayout(inner)
        grid.setContentsMargins(0, 8, 0, 0)
        grid.setSpacing(12)
        for index, (glyph, title, note_text) in enumerate(SKILL_CARDS):
            grid.addWidget(_skill_card(glyph, title, note_text), index // 2, index % 2)
        grid.setRowStretch(len(SKILL_CARDS) // 2 + 1, 1)

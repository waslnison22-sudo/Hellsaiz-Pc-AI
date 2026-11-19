"""Page «Что я умею?» — honest capability cards, no invented features.

Every card mirrors real commands from core/commands.py HELP_TEXT.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

SKILL_CARDS: tuple[tuple[str, str, str], ...] = (
    ("🚀", "Программы", "Запуск разрешённых приложений по имени: блокнот, калькулятор, проводник, игры."),
    ("🪟", "Окна", "«Покажи открытые окна», «переключись на Блокнот», «сверни окно», «заблокируй компьютер»."),
    ("🔊", "Звук и медиа", "Громкость шагом («громче», «громче на 20»), пауза и треки, «включи музыку дождь»."),
    ("🌐", "Сеть и VPN", "«Включи впн», «выключи впн», «проверь впн» — через локальный клиент v2RayTun."),
    ("⏰", "Напоминания", "«Напомни через 5 минут…», «напомни в 22:00…», «мои напоминания» — до 30 дней."),
    ("🌦", "Погода и курсы", "«Погода в Москве», «собираюсь погулять», «курс доллара к рублю»."),
    ("🧮", "Счёт и поиск", "«Сколько будет 12 умножить на 3», «найди в интернете…», «открой сайт example.com»."),
    ("📁", "Файлы и буфер", "«Покажи файлы в папке Документы», «прочитай файл…», «скопируй…», «что в буфере обмена»."),
    ("👁", "Экран и окна-контролы", "«Прочитай текст на экране», «нажми Сохранить в окне Блокнот», «введи текст в поле…»."),
    ("🎬", "Сценарии", "Своя автоматизация: цепочки действий по расписанию, автозапуску и горячей клавише."),
    ("🎙", "Голос", "Wake-слово «Хеллсайз», локальное распознавание речи и озвучка ответов."),
    ("🔒", "Приватность", "Всё локально: никакие команды и разговоры не уходят в сеть. Произвольный код не запускается."),
)


def _skill_card(glyph: str, title: str, note: str) -> QFrame:
    card = QFrame()
    card.setObjectName("skillCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)
    title_label = QLabel(f"{glyph}  {title}")
    title_label.setObjectName("skillCardTitle")
    title_label.setWordWrap(True)
    layout.addWidget(title_label)
    note_label = QLabel(note)
    note_label.setObjectName("skillCardNote")
    note_label.setWordWrap(True)
    layout.addWidget(note_label)
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

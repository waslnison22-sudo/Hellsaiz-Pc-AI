"""Persona dialog: name, character, style, voice and companion model."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hellsaiz_pc_ai.app import persona as persona_module


class PersonaDialog(QDialog):
    """One window that ties prompt, voice and companion model together."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        persona: persona_module.Persona,
        personas: list[persona_module.Persona],
        models: list[dict],
        voices: list[str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Персона ассистента")
        self.setObjectName("personaDialog")
        self.resize(560, 520)
        self._persona = persona
        self._personas = personas or [persona]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("Персона")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        hint = QLabel(
            "Имя, характер и стиль попадают в системный промпт как установки владельца."
        )
        hint.setObjectName("secondaryText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit(persona.name)
        self.name_edit.setMaxLength(persona_module.MAX_NAME)
        form.addRow("Имя", self.name_edit)

        self.character_edit = QTextEdit(persona.character)
        self.character_edit.setMinimumHeight(120)
        form.addRow("Характер", self.character_edit)

        presets_row = QHBoxLayout()
        presets_row.setSpacing(6)
        for name, text in persona_module.PRESETS.items():
            button = QPushButton(name)
            button.setObjectName("secondaryButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=text: self.character_edit.setPlainText(value))
            presets_row.addWidget(button)
        presets_row.addStretch(1)
        form.addRow("Пресеты", self._wrap(presets_row))

        self.length_combo = QComboBox()
        self.length_combo.addItems(persona_module.LENGTH_CHOICES)
        self.length_combo.setCurrentText(persona.length)
        form.addRow("Длина ответов", self.length_combo)

        self.tone_combo = QComboBox()
        self.tone_combo.addItems(persona_module.TONE_CHOICES)
        self.tone_combo.setCurrentText(persona.tone)
        form.addRow("Стиль", self.tone_combo)

        self.voice_combo = QComboBox()
        self.voice_combo.addItem("Системный голос", "")
        for voice in voices:
            self.voice_combo.addItem(voice, voice)
        index = self.voice_combo.findData(persona.voice_id)
        self.voice_combo.setCurrentIndex(index if index >= 0 else 0)
        form.addRow("Голос", self.voice_combo)

        self.model_combo = QComboBox()
        self.model_combo.addItem("Встроенная модель", "")
        for item in models:
            self.model_combo.addItem(str(item.get("display_name") or item.get("model_id")), item.get("model_id"))
        index = self.model_combo.findData(persona.model_slug)
        self.model_combo.setCurrentIndex(index if index >= 0 else 0)
        form.addRow("Модель компаньона", self.model_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _wrap(layout: QHBoxLayout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        return holder

    def result_persona(self) -> persona_module.Persona:
        return persona_module.Persona(
            persona_id=self._persona.persona_id,
            name=self.name_edit.text(),
            character=self.character_edit.toPlainText(),
            length=self.length_combo.currentText(),
            tone=self.tone_combo.currentText(),
            voice_id=str(self.voice_combo.currentData() or ""),
            model_slug=str(self.model_combo.currentData() or ""),
        ).normalised()

    def save(self, path: Path) -> persona_module.Persona:
        updated = self.result_persona()
        replaced = False
        personas: list[persona_module.Persona] = []
        for item in self._personas:
            if item.persona_id == updated.persona_id:
                personas.append(updated)
                replaced = True
            else:
                personas.append(item)
        if not replaced:
            personas.append(updated)
        persona_module.save_personas(path, personas, updated.persona_id)
        return updated

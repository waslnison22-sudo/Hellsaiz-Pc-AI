from __future__ import annotations

import copy
import json
import uuid
from typing import Any

from PySide6.QtCore import Qt, QTime, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec
from hellsaiz_pc_ai.workflows.graph import GraphNode, WorkflowGraph
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary
from hellsaiz_pc_ai.workflows.qt_canvas import WorkflowCanvas
from hellsaiz_pc_ai.workflows.studio_model import (
    ACTION_LABELS,
    build_workflow_graph,
    describe_action,
    describe_trigger,
    workflow_to_draft,
)


TOOL_TITLES = {
    "set_volume": "Изменить громкость",
    "open_app": "Открыть приложение",
    "open_url": "Открыть сайт",
    "lock_pc": "Заблокировать компьютер",
    "close_process": "Закрыть приложение",
    "get_local_time": "Показать текущее время",
    "get_system_info": "Сведения о компьютере",
    "read_clipboard": "Прочитать буфер обмена",
    "write_clipboard": "Скопировать текст",
    "create_folder": "Создать папку",
    "create_text_file": "Создать текстовый файл",
    "search_files": "Найти файл",
    "read_text_file": "Прочитать текстовый файл",
    "open_file": "Открыть файл",
    "get_window_list": "Показать открытые окна",
    "focus_window": "Переключиться на окно",
    "minimize_window": "Свернуть окно",
    "maximize_window": "Развернуть окно",
    "restore_window": "Восстановить окно",
    "close_window": "Закрыть окно",
    "inspect_window": "Посмотреть элементы окна",
    "click_ui_element": "Нажать элемент окна",
    "type_ui_text": "Ввести текст в окно",
    "read_screen_text": "Распознать текст на экране",
    "create_reminder": "Создать напоминание",
}

FIELD_TITLES = {
    "app": "Приложение",
    "process": "Приложение или процесс",
    "percent": "Громкость, %",
    "url": "Адрес сайта",
    "seconds": "Сколько секунд",
    "text": "Текст",
    "path": "Путь к файлу или папке",
    "folder": "Папка",
    "query": "Что найти",
    "title": "Название окна",
    "window_title": "Название окна",
    "element_name": "Название элемента",
    "name": "Название",
    "message": "Текст напоминания",
    "delay_seconds": "Через сколько секунд",
    "shortcut": "Сочетание клавиш",
}

FIELD_HINTS = {
    "app": "Выбери приложение из разрешённого каталога.",
    "process": "Выбери процесс из разрешённого списка.",
    "url": "Например, https://example.com",
    "text": "Введи обычный текст.",
    "title": "Можно указать часть заголовка окна.",
    "window_title": "Можно указать часть заголовка окна.",
}

WEEKDAYS = (
    ("Понедельник", 1),
    ("Вторник", 2),
    ("Среда", 3),
    ("Четверг", 4),
    ("Пятница", 5),
    ("Суббота", 6),
    ("Воскресенье", 7),
)

HOTKEYS = (
    "Ctrl+Alt+H",
    "Ctrl+Alt+J",
    "Ctrl+Alt+K",
    "Ctrl+Alt+M",
    "Ctrl+Shift+H",
    "Ctrl+Shift+J",
    "Alt+Shift+H",
)

CONDITION_OPERATORS = (
    ("не раньше", "gte"),
    ("позже", "gt"),
    ("ровно", "eq"),
    ("не позже", "lte"),
    ("раньше", "lt"),
)


def _friendly_tool_title(spec: ToolSpec) -> str:
    return TOOL_TITLES.get(
        spec.name,
        ACTION_LABELS.get(spec.name, spec.name.replace("_", " ").capitalize()),
    )


def _friendly_field_title(name: str, schema: dict[str, Any]) -> str:
    return str(schema.get("title") or FIELD_TITLES.get(name, name.replace("_", " ").capitalize()))


def _schema_is_supported(spec: ToolSpec) -> bool:
    parameters = spec.parameters
    properties = parameters.get("properties", {})
    if parameters.get("type") != "object" or not isinstance(properties, dict):
        return False
    for schema in properties.values():
        if not isinstance(schema, dict):
            return False
        if schema.get("type") not in {"string", "integer", "number", "boolean"}:
            return False
    return True


def _default_draft() -> dict[str, Any]:
    return {
        "name": "Новый сценарий",
        "trigger_kind": "text",
        "trigger_config": {"phrase": ""},
        "actions": [],
        "condition": None,
        "true_actions": [],
        "false_actions": [],
    }


def _make_templates(allowed_apps: dict[str, Any]) -> list[dict[str, Any]]:
    app_alias = next(iter(allowed_apps), None)
    gaming_actions = [
        {"kind": "tool", "name": "set_volume", "arguments": {"percent": 70}}
    ]
    if app_alias:
        gaming_actions.append(
            {"kind": "tool", "name": "open_app", "arguments": {"app": app_alias}}
        )

    home_actions = [
        {"kind": "tool", "name": "set_volume", "arguments": {"percent": 35}}
    ]
    if app_alias:
        home_actions.append(
            {"kind": "tool", "name": "open_app", "arguments": {"app": app_alias}}
        )

    return [
        {
            "title": "Режим «Я дома»",
            "description": (
                "Пример по принципу сценариев Алисы: скажи «я дома», и помощник "
                "выполнит действия на этом компьютере. Управления лампами, розетками "
                "и климатом пока нет."
            ),
            "draft": {
                **_default_draft(),
                "name": "Режим «Я дома»",
                "trigger_config": {"phrases": ["я дома", "я вернулся"]},
                "actions": home_actions,
            },
        },
        {
            "title": "Тихий вечер",
            "description": "Фраза «тихий вечер» устанавливает системную громкость на 25%.",
            "draft": {
                **_default_draft(),
                "name": "Тихий вечер",
                "trigger_config": {"phrases": ["тихий вечер", "сделай потише"]},
                "actions": [
                    {"kind": "tool", "name": "set_volume", "arguments": {"percent": 25}}
                ],
            },
        },
        {
            "title": "Рабочее утро",
            "description": "По будням в 09:00 показывает текущее локальное время.",
            "draft": {
                **_default_draft(),
                "name": "Рабочее утро",
                "trigger_kind": "schedule",
                "trigger_config": {"time": "09:00", "days": [1, 2, 3, 4, 5]},
                "actions": [
                    {"kind": "tool", "name": "get_local_time", "arguments": {}}
                ],
            },
        },
        {
            "title": "Игровой режим",
            "description": (
                "Фраза «игровой режим» меняет громкость и, если приложение уже "
                "добавлено в разрешённый каталог, открывает его."
            ),
            "draft": {
                **_default_draft(),
                "name": "Игровой режим",
                "trigger_config": {"phrases": ["игровой режим", "пора играть"]},
                "actions": gaming_actions,
            },
        },
        {
            "title": "Спокойной ночи",
            "description": (
                "Проверяет время: после 22:00 ставит громкость 15%, "
                "в остальное время — 30%."
            ),
            "draft": {
                **_default_draft(),
                "name": "Спокойной ночи",
                "trigger_config": {"phrases": ["спокойной ночи", "пора спать"]},
                "condition": {"kind": "hour", "operator": "gte", "value": 22},
                "true_actions": [
                    {"kind": "tool", "name": "set_volume", "arguments": {"percent": 15}}
                ],
                "false_actions": [
                    {"kind": "tool", "name": "set_volume", "arguments": {"percent": 30}}
                ],
            },
        },
    ]


class TemplateGalleryDialog(QDialog):
    def __init__(self, templates: list[dict[str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Готовые сценарии")
        self.setMinimumSize(520, 420)
        self.selected_draft: dict[str, Any] | None = None
        layout = QVBoxLayout(self)
        title = QLabel("Выбери готовый пример")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.list_widget = QListWidget()
        self.description = QLabel("Выбери сценарий, чтобы посмотреть, что он делает.")
        self.description.setWordWrap(True)
        self.description.setObjectName("secondaryText")
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.description)
        for index, template in enumerate(templates):
            item = QListWidgetItem(template["title"])
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.list_widget.addItem(item)
        self.list_widget.currentRowChanged.connect(self._show_description)
        if templates:
            self.list_widget.setCurrentRow(0)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Использовать шаблон")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._choose)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._templates = templates

    def _show_description(self, row: int) -> None:
        if 0 <= row < len(self._templates):
            self.description.setText(self._templates[row]["description"])

    def _choose(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._templates):
            self.selected_draft = copy.deepcopy(self._templates[row]["draft"])
            self.accept()


class ActionPickerDialog(QDialog):
    def __init__(self, specs: list[ToolSpec], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Добавить действие")
        self.setMinimumSize(480, 420)
        self.selected_name: str | None = None
        self._specs = specs
        layout = QVBoxLayout(self)
        title = QLabel("Что должен сделать помощник?")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        subtitle = QLabel("Выбери понятное действие. Его параметры можно настроить следующим шагом.")
        subtitle.setObjectName("secondaryText")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        self.list_widget = QListWidget()
        self._names: list[str] = ["__wait__"]
        wait_item = QListWidgetItem("Подождать")
        wait_item.setToolTip("Добавить небольшую паузу перед следующим действием.")
        self.list_widget.addItem(wait_item)
        for spec in specs:
            item = QListWidgetItem(_friendly_tool_title(spec))
            item.setToolTip(spec.description)
            item.setData(Qt.ItemDataRole.UserRole, spec.name)
            self.list_widget.addItem(item)
            self._names.append(spec.name)
        layout.addWidget(self.list_widget, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Далее")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._choose)
        buttons.rejected.connect(self.reject)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._choose())
        layout.addWidget(buttons)
        self.list_widget.setCurrentRow(0)

    def _choose(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        self.selected_name = item.data(Qt.ItemDataRole.UserRole) or "__wait__"
        self.accept()


class PauseActionDialog(QDialog):
    def __init__(self, seconds: float = 1.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настроить паузу")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Сколько секунд подождать перед следующим действием?"))
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(0.1, 30.0)
        self.seconds.setDecimals(1)
        self.seconds.setSingleStep(0.5)
        self.seconds.setSuffix(" сек.")
        self.seconds.setValue(max(0.1, min(float(seconds), 30.0)))
        layout.addWidget(self.seconds)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ToolActionDialog(QDialog):
    def __init__(
        self,
        registry: ToolRegistry,
        spec: ToolSpec,
        *,
        initial: dict[str, Any] | None = None,
        allowed_apps: dict[str, Any] | None = None,
        allowed_processes: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.registry = registry
        self.spec = spec
        self.initial = initial or {}
        self.allowed_apps = allowed_apps or {}
        self.allowed_processes = allowed_processes or {}
        self.result_action: dict[str, Any] | None = None
        self.fields: dict[str, Any] = {}
        self.required = set(spec.parameters.get("required", []))
        self.setWindowTitle(_friendly_tool_title(spec))
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        title = QLabel(_friendly_tool_title(spec))
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        description = QLabel(spec.description)
        description.setObjectName("secondaryText")
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        properties = spec.parameters.get("properties", {})
        arguments = dict(self.initial.get("arguments", {}))
        for name, schema in properties.items():
            control = self._create_field(name, schema, arguments.get(name))
            self.fields[name] = control
            form.addRow(_friendly_field_title(name, schema), control)
        layout.addLayout(form)
        repeat_group = QGroupBox("Повторить это действие")
        repeat_group.setCheckable(True)
        repeat_group.setChecked(self.initial.get("kind") == "repeat")
        repeat_layout = QHBoxLayout(repeat_group)
        repeat_layout.addWidget(QLabel("Количество повторов"))
        self.repeat_count = QSpinBox()
        self.repeat_count.setRange(1, 10)
        self.repeat_count.setValue(int(self.initial.get("count", 2)))
        repeat_layout.addWidget(self.repeat_count)
        repeat_layout.addStretch(1)
        layout.addWidget(repeat_group)
        self.repeat_group = repeat_group
        if spec.name == "lock_pc":
            warning = QLabel("После запуска Windows заблокирует текущую сессию.")
            warning.setObjectName("warningText")
            layout.addWidget(warning)
        elif spec.name == "close_process":
            warning = QLabel("Будет выполнено штатное завершение выбранного процесса.")
            warning.setObjectName("warningText")
            layout.addWidget(warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Добавить действие")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._accept_action)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_field(self, name: str, schema: dict[str, Any], initial: Any) -> QWidget:
        value_type = schema.get("type")
        if value_type == "string" and name == "app":
            widget = QComboBox()
            for alias in self.allowed_apps:
                widget.addItem(alias.replace("_", " ").title(), alias)
            if initial is not None:
                index = widget.findData(initial)
                if index >= 0:
                    widget.setCurrentIndex(index)
            return widget
        if value_type == "string" and name == "process":
            widget = QComboBox()
            for alias in self.allowed_processes:
                widget.addItem(alias.replace("_", " ").title(), alias)
            if initial is not None:
                index = widget.findData(initial)
                if index >= 0:
                    widget.setCurrentIndex(index)
            return widget
        if value_type == "string" and "enum" in schema:
            widget = QComboBox()
            for option in schema.get("enum", []):
                widget.addItem(str(option), option)
            if initial is not None:
                index = widget.findData(initial)
                if index >= 0:
                    widget.setCurrentIndex(index)
            return widget
        if value_type == "string":
            widget = QLineEdit(str(initial or ""))
            widget.setPlaceholderText(
                FIELD_HINTS.get(name, str(schema.get("description") or "Введите значение"))
            )
            if "maxLength" in schema:
                widget.setMaxLength(int(schema["maxLength"]))
            return widget
        if value_type == "integer":
            widget = QSpinBox()
            widget.setRange(
                int(schema.get("minimum", -100000)),
                int(schema.get("maximum", 100000)),
            )
            widget.setValue(int(initial if initial is not None else schema.get("minimum", 0)))
            return widget
        if value_type == "number":
            widget = QDoubleSpinBox()
            widget.setRange(
                float(schema.get("minimum", -100000)),
                float(schema.get("maximum", 100000)),
            )
            widget.setDecimals(2)
            widget.setValue(float(initial if initial is not None else schema.get("minimum", 0)))
            return widget
        widget = QCheckBox()
        widget.setChecked(bool(initial))
        return widget

    def _read_arguments(self) -> dict[str, Any]:
        arguments: dict[str, Any] = {}
        for name, control in self.fields.items():
            if isinstance(control, QComboBox):
                value = control.currentData()
                if value is None:
                    value = control.currentText().strip()
            elif isinstance(control, QLineEdit):
                value = control.text().strip()
            elif isinstance(control, QSpinBox):
                value = control.value()
            elif isinstance(control, QDoubleSpinBox):
                value = control.value()
            else:
                value = control.isChecked()
            if isinstance(control, QLineEdit) and not value and name not in self.required:
                continue
            arguments[name] = value
        return arguments

    def _accept_action(self) -> None:
        arguments = self._read_arguments()
        validation = self.registry.validate_arguments(self.spec.name, arguments)
        if not validation.ok:
            QMessageBox.warning(self, "Проверь параметры", validation.output)
            return
        self.result_action = {
            "kind": "repeat" if self.repeat_group.isChecked() else "tool",
            "name": self.spec.name,
            "arguments": arguments,
        }
        if self.repeat_group.isChecked():
            self.result_action["count"] = self.repeat_count.value()
        self.accept()


class ActionCard(QFrame):
    def __init__(
        self,
        title: str,
        description: str,
        on_edit,
        on_up,
        on_down,
        on_remove,
        *,
        first: bool,
        last: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("scenarioActionCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 10, 9)
        text_layout = QVBoxLayout()
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        detail = QLabel(description)
        detail.setObjectName("secondaryText")
        detail.setWordWrap(True)
        text_layout.addWidget(heading)
        text_layout.addWidget(detail)
        layout.addLayout(text_layout, 1)
        up_button = QPushButton("↑")
        up_button.setObjectName("toolbarButton")
        up_button.setToolTip("Переместить выше")
        up_button.setEnabled(not first)
        up_button.clicked.connect(on_up)
        down_button = QPushButton("↓")
        down_button.setObjectName("toolbarButton")
        down_button.setToolTip("Переместить ниже")
        down_button.setEnabled(not last)
        down_button.clicked.connect(on_down)
        edit_button = QPushButton("Изменить")
        edit_button.setObjectName("toolbarButton")
        edit_button.clicked.connect(on_edit)
        remove_button = QPushButton("Убрать")
        remove_button.setObjectName("toolbarButton")
        remove_button.clicked.connect(on_remove)
        layout.addWidget(up_button)
        layout.addWidget(down_button)
        layout.addWidget(edit_button)
        layout.addWidget(remove_button)


class WorkflowStudioPage(QWidget):
    """A guided, non-code editor for the application's validated workflow graphs."""

    run_requested = Signal(str, str, str)

    def __init__(
        self,
        workflow_library: WorkflowLibrary,
        registry: ToolRegistry,
        allowed_apps: dict[str, Any] | None = None,
        allowed_processes: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workflow_library = workflow_library
        self.registry = registry
        self.allowed_apps = allowed_apps or {}
        self.allowed_processes = allowed_processes or {}
        self._workflow_id: str | None = None
        self._selected_graph: WorkflowGraph | None = None
        self._editable = True
        self._loading = False
        self._dirty = False
        self._actions: dict[str, list[dict[str, Any]]] = {
            "main": [],
            "true": [],
            "false": [],
        }
        self._tool_specs = self._available_tool_specs()
        self._build_ui()
        self._set_draft(_default_draft())
        self._refresh_library()

    def _available_tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for schema in self.registry.openai_schemas():
            function = schema.get("function", {})
            name = function.get("name")
            spec = self.registry.get_spec(name) if isinstance(name, str) else None
            if spec is None or not _schema_is_supported(spec):
                continue
            if spec.name == "open_app" and not self.allowed_apps:
                continue
            if spec.name == "close_process" and not self.allowed_processes:
                continue
            specs.append(spec)
        return specs

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        header_text = QVBoxLayout()
        title = QLabel("СЦЕНАРИИ")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Собирай автоматизации из понятных блоков — без программирования и JSON.")
        subtitle.setObjectName("secondaryText")
        subtitle.setWordWrap(True)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header.addLayout(header_text, 1)
        self.new_button = QPushButton("Новый сценарий")
        self.new_button.setObjectName("primaryButton")
        self.template_button = QPushButton("Готовые шаблоны")
        header.addWidget(self.template_button)
        header.addWidget(self.new_button)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        library_panel = QFrame()
        library_panel.setObjectName("studioPanel")
        library_layout = QVBoxLayout(library_panel)
        library_layout.setContentsMargins(12, 12, 12, 12)
        library_title = QLabel("МОЯ БИБЛИОТЕКА")
        library_title.setObjectName("sectionEyebrow")
        library_layout.addWidget(library_title)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Найти сценарий…")
        library_layout.addWidget(self.search_edit)
        self.scenario_list = QListWidget()
        self.scenario_list.setAccessibleName("Сохранённые сценарии")
        self.scenario_list.setToolTip("Выбери сценарий, чтобы посмотреть или изменить его.")
        library_layout.addWidget(self.scenario_list, 1)
        self.delete_button = QPushButton("Удалить выбранный")
        library_layout.addWidget(self.delete_button)
        splitter.addWidget(library_panel)

        self.detail_tabs = QTabWidget()
        self.builder_tab = QWidget()
        builder_outer = QVBoxLayout(self.builder_tab)
        builder_outer.setContentsMargins(8, 8, 8, 8)
        self.editability_notice = QLabel(
            "Этот сценарий использует сложные блоки. Его можно просмотреть и запустить, "
            "но простой редактор пока не может безопасно изменить его структуру."
        )
        self.editability_notice.setObjectName("warningText")
        self.editability_notice.setWordWrap(True)
        self.editability_notice.hide()
        builder_outer.addWidget(self.editability_notice)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.builder_fields = QWidget()
        self.builder_fields_layout = QVBoxLayout(self.builder_fields)
        self.builder_fields_layout.setContentsMargins(4, 4, 8, 8)
        self.builder_fields_layout.setSpacing(12)
        name_group = QGroupBox("Название сценария")
        name_group.setObjectName("scenarioCard")
        name_layout = QVBoxLayout(name_group)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Например, Тихий вечер или Игровой режим")
        name_layout.addWidget(self.name_edit)
        self.builder_fields_layout.addWidget(name_group)
        self.name_edit.textChanged.connect(self._mark_dirty)
        self._build_trigger_section()
        self._build_condition_section()
        self._build_action_sections()
        scroll.setWidget(self.builder_fields)
        builder_outer.addWidget(scroll, 1)
        self.detail_tabs.addTab(self.builder_tab, "Простой конструктор")

        map_tab = QWidget()
        map_layout = QVBoxLayout(map_tab)
        map_toolbar = QHBoxLayout()
        map_hint = QLabel("Перетаскивай блоки, чтобы изменить расположение схемы.")
        map_hint.setObjectName("secondaryText")
        self.fit_button = QPushButton("По размеру")
        self.reset_layout_button = QPushButton("Сбросить расположение")
        map_toolbar.addWidget(map_hint, 1)
        map_toolbar.addWidget(self.fit_button)
        map_toolbar.addWidget(self.reset_layout_button)
        map_layout.addLayout(map_toolbar)
        self.graph_view = WorkflowCanvas()
        map_layout.addWidget(self.graph_view, 1)
        self.detail_tabs.addTab(map_tab, "Схема")

        technical_tab = QWidget()
        technical_layout = QVBoxLayout(technical_tab)
        technical_hint = QLabel(
            "Режим для разработчиков. Здесь можно просматривать и изменять полный граф "
            "сценария. Перед сохранением схема проходит тот же валидатор, что и обычные сценарии."
        )
        technical_hint.setObjectName("secondaryText")
        technical_hint.setWordWrap(True)
        technical_layout.addWidget(technical_hint)
        self.technical_json = QPlainTextEdit()
        self.technical_json.setPlaceholderText("Схема появится после создания или выбора сценария.")
        self.technical_json.setFont(QFont("Consolas", 9))
        technical_layout.addWidget(self.technical_json, 1)
        technical_buttons = QHBoxLayout()
        self.apply_json_button = QPushButton("Проверить и сохранить JSON")
        self.apply_json_button.setObjectName("primaryButton")
        self.apply_json_button.clicked.connect(self._apply_technical_schema)
        copy_json_button = QPushButton("Скопировать схему")
        copy_json_button.clicked.connect(self._copy_technical_schema)
        technical_buttons.addWidget(self.apply_json_button)
        technical_buttons.addWidget(copy_json_button)
        technical_layout.addLayout(technical_buttons)
        self.detail_tabs.addTab(technical_tab, "Для разработчиков")

        splitter.addWidget(self.detail_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        root.addWidget(splitter, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel("Сценарии сохраняются только на этом компьютере.")
        self.status_label.setObjectName("scenarioStatus")
        footer.addWidget(self.status_label, 1)
        self.save_button = QPushButton("Сохранить")
        self.save_button.setObjectName("primaryButton")
        self.run_button = QPushButton("Запустить сейчас")
        self.run_button.setEnabled(False)
        footer.addWidget(self.save_button)
        footer.addWidget(self.run_button)
        root.addLayout(footer)

        self.new_button.clicked.connect(self.new_scenario)
        self.template_button.clicked.connect(self.choose_template)
        self.delete_button.clicked.connect(self.delete_selected)
        self.save_button.clicked.connect(self.save_current)
        self.run_button.clicked.connect(self.run_current)
        self.search_edit.textChanged.connect(self._refresh_library)
        self.scenario_list.itemSelectionChanged.connect(self.load_selected)
        self.fit_button.clicked.connect(self.graph_view.fit_graph)
        self.reset_layout_button.clicked.connect(self._reset_canvas_layout)
        self.graph_view.node_double_clicked.connect(self._edit_graph_node)

    def _copy_technical_schema(self) -> None:
        self.technical_json.selectAll()
        self.technical_json.copy()

    def _edit_graph_node(self, node_id: str) -> None:
        if self._editable:
            try:
                graph = self._build_current_graph()
            except (ValueError, TypeError, KeyError):
                graph = self._selected_graph
        else:
            graph = self._selected_graph
        if graph is None:
            return
        node = next((item for item in graph.nodes if item.id == node_id), None)
        if node is None:
            return
        if not self._editable:
            self.detail_tabs.setCurrentIndex(2)
            self.technical_json.setFocus()
            self.status_label.setText(
                "Этот сложный блок редактируется в режиме «Для разработчиков»."
            )
            return
        self.detail_tabs.setCurrentIndex(0)
        if node.kind.startswith("trigger."):
            self.trigger_combo.setFocus()
            self.status_label.setText("Измени способ запуска в первом блоке конструктора.")
            return
        if node.kind.startswith("condition."):
            self.condition_group.setFocus()
            self.status_label.setText("Измени условие в разделе «Условие».")
            return
        if node.id.startswith("true_"):
            branch = "true"
            suffix = node.id.removeprefix("true_")
        elif node.id.startswith("false_"):
            branch = "false"
            suffix = node.id.removeprefix("false_")
        elif node.id.startswith("action_"):
            branch = "main"
            suffix = node.id.removeprefix("action_")
        else:
            self.detail_tabs.setCurrentIndex(2)
            self.technical_json.setFocus()
            self.status_label.setText(
                "Для этого блока открылся режим «Для разработчиков»."
            )
            return
        try:
            index = int(suffix) - 1
        except ValueError:
            self.detail_tabs.setCurrentIndex(2)
            self.technical_json.setFocus()
            return
        self.edit_action(branch, index)

    def _apply_technical_schema(self) -> None:
        try:
            # The graph validator is the source of truth for the developer editor.
            # Legacy tool names may no longer be registered, but their graph must remain
            # editable and round-trippable rather than being silently discarded.
            graph = WorkflowGraph.from_dict(json.loads(self.technical_json.toPlainText()))
            workflow_id = self._workflow_id or f"scenario-{uuid.uuid4().hex[:8]}"
            positions = (
                self.graph_view.export_layout()
                if self._workflow_id == workflow_id else {}
            )
            self.workflow_library.save(workflow_id, graph)
            self.graph_view.set_graph(graph, positions)
            self.workflow_library.save_layout(workflow_id, self.graph_view.export_layout())
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.status_label.setText(f"JSON не прошёл проверку: {exc}")
            return

        self._workflow_id = workflow_id
        self._selected_graph = graph
        try:
            draft = workflow_to_draft(graph)
        except ValueError as exc:
            self._set_read_only_graph(
                graph,
                f"Схема сохранена. У неё есть расширенная логика: {exc} "
                "Для дальнейшего редактирования используй режим «Для разработчиков».",
            )
        else:
            self._set_draft(draft)
            self._selected_graph = graph
            self._dirty = False
            self._update_preview(graph)
        self._refresh_library(select_id=workflow_id)
        self.detail_tabs.setCurrentIndex(2)
        self.status_label.setText(
            f"Сценарий «{graph.name}» проверен и сохранён. Структура графа корректна."
        )

    def _build_trigger_section(self) -> None:
        group = QGroupBox("1. Когда запускать сценарий?")
        group.setObjectName("scenarioCard")
        layout = QVBoxLayout(group)
        self.trigger_combo = QComboBox()
        self.trigger_combo.addItem("Когда я произнесу фразу", "text")
        self.trigger_combo.addItem("По расписанию", "schedule")
        self.trigger_combo.addItem("По сочетанию клавиш", "hotkey")
        self.trigger_combo.addItem("При запуске приложения", "startup")
        layout.addWidget(self.trigger_combo)
        self.trigger_stack = QStackedWidget()
        phrase_page = QWidget()
        phrase_layout = QVBoxLayout(phrase_page)
        self.phrase_edit = QLineEdit()
        self.phrase_edit.setPlaceholderText("Например: ночной режим, спокойной ночи")
        phrase_help = QLabel("Несколько фраз разделяй запятыми. Любая из них запустит сценарий.")
        phrase_help.setObjectName("secondaryText")
        phrase_layout.addWidget(self.phrase_edit)
        phrase_layout.addWidget(phrase_help)
        self.trigger_stack.addWidget(phrase_page)

        schedule_page = QWidget()
        schedule_layout = QVBoxLayout(schedule_page)
        schedule_row = QHBoxLayout()
        schedule_row.addWidget(QLabel("Время"))
        self.schedule_time = QTimeEdit()
        self.schedule_time.setDisplayFormat("HH:mm")
        self.schedule_time.setTime(QTime(9, 0))
        schedule_row.addWidget(self.schedule_time)
        schedule_row.addStretch(1)
        schedule_layout.addLayout(schedule_row)
        days_grid = QGridLayout()
        self.day_checks: dict[int, QCheckBox] = {}
        for index, (label, number) in enumerate(WEEKDAYS):
            check = QCheckBox(label)
            check.setChecked(number <= 5)
            self.day_checks[number] = check
            days_grid.addWidget(check, index // 4, index % 4)
        schedule_layout.addLayout(days_grid)
        schedule_layout.addWidget(QLabel("Отметь дни, в которые нужно повторять сценарий."))
        self.trigger_stack.addWidget(schedule_page)

        hotkey_page = QWidget()
        hotkey_layout = QVBoxLayout(hotkey_page)
        hotkey_layout.addWidget(QLabel("Выбери свободное сочетание клавиш:"))
        self.hotkey_combo = QComboBox()
        for combo in HOTKEYS:
            self.hotkey_combo.addItem(combo, combo)
        hotkey_layout.addWidget(self.hotkey_combo)
        hotkey_layout.addStretch(1)
        self.trigger_stack.addWidget(hotkey_page)

        startup_page = QWidget()
        startup_layout = QVBoxLayout(startup_page)
        startup_layout.addWidget(QLabel("Сценарий выполнится один раз при запуске Hellsaiz PC AI."))
        startup_layout.addStretch(1)
        self.trigger_stack.addWidget(startup_page)
        layout.addWidget(self.trigger_stack)
        self.builder_fields_layout.addWidget(group)
        self.trigger_combo.currentIndexChanged.connect(self._sync_trigger_page)
        self.trigger_combo.currentIndexChanged.connect(self._mark_dirty)
        self.phrase_edit.textChanged.connect(self._mark_dirty)
        self.schedule_time.timeChanged.connect(self._mark_dirty)
        self.hotkey_combo.currentIndexChanged.connect(self._mark_dirty)
        for check in self.day_checks.values():
            check.toggled.connect(self._mark_dirty)
        self._sync_trigger_page()

    def _build_condition_section(self) -> None:
        self.condition_group = QGroupBox("2. Добавить условие (необязательно)")
        self.condition_group.setObjectName("scenarioCard")
        self.condition_group.setCheckable(True)
        self.condition_group.setChecked(False)
        layout = QVBoxLayout(self.condition_group)
        self.condition_kind_combo = QComboBox()
        self.condition_kind_combo.addItem("Проверить время", "hour")
        self.condition_kind_combo.addItem("Проверить день недели", "weekday")
        layout.addWidget(self.condition_kind_combo)
        self.condition_stack = QStackedWidget()
        hour_page = QWidget()
        hour_layout = QHBoxLayout(hour_page)
        self.hour_operator = QComboBox()
        for label, value in CONDITION_OPERATORS:
            self.hour_operator.addItem(label, value)
        self.hour_value = QSpinBox()
        self.hour_value.setRange(0, 23)
        self.hour_value.setValue(22)
        hour_layout.addWidget(QLabel("Час"))
        hour_layout.addWidget(self.hour_operator)
        hour_layout.addWidget(self.hour_value)
        hour_layout.addStretch(1)
        self.condition_stack.addWidget(hour_page)
        weekday_page = QWidget()
        weekday_layout = QHBoxLayout(weekday_page)
        self.condition_weekday = QComboBox()
        for label, value in WEEKDAYS:
            self.condition_weekday.addItem(label, value)
        weekday_layout.addWidget(QLabel("День"))
        weekday_layout.addWidget(self.condition_weekday)
        weekday_layout.addStretch(1)
        self.condition_stack.addWidget(weekday_page)
        layout.addWidget(self.condition_stack)
        self.builder_fields_layout.addWidget(self.condition_group)
        self.condition_group.toggled.connect(self._sync_action_sections)
        self.condition_group.toggled.connect(self._mark_dirty)
        self.condition_kind_combo.currentIndexChanged.connect(self._sync_condition_page)
        self.condition_kind_combo.currentIndexChanged.connect(self._mark_dirty)
        self.hour_operator.currentIndexChanged.connect(self._mark_dirty)
        self.hour_value.valueChanged.connect(self._mark_dirty)
        self.condition_weekday.currentIndexChanged.connect(self._mark_dirty)
        self._sync_condition_page()

    def _build_action_sections(self) -> None:
        self.linear_group = QGroupBox("3. Что сделать?")
        self.linear_group.setObjectName("scenarioCard")
        self.linear_layout = QVBoxLayout(self.linear_group)
        self.linear_actions_layout = QVBoxLayout()
        self.linear_layout.addLayout(self.linear_actions_layout)
        linear_add = QPushButton("Добавить действие")
        linear_add.clicked.connect(lambda: self.add_action("main"))
        self.linear_layout.addWidget(linear_add)
        self.builder_fields_layout.addWidget(self.linear_group)

        self.branches_container = QWidget()
        branches_layout = QHBoxLayout(self.branches_container)
        branches_layout.setContentsMargins(0, 0, 0, 0)
        self.true_group = QGroupBox("Если условие выполнено")
        self.true_group.setObjectName("scenarioBranchCard")
        self.true_layout = QVBoxLayout(self.true_group)
        self.true_actions_layout = QVBoxLayout()
        self.true_layout.addLayout(self.true_actions_layout)
        true_add = QPushButton("Добавить действие")
        true_add.clicked.connect(lambda: self.add_action("true"))
        self.true_layout.addWidget(true_add)
        self.false_group = QGroupBox("Если условие не выполнено")
        self.false_group.setObjectName("scenarioBranchCard")
        self.false_layout = QVBoxLayout(self.false_group)
        self.false_actions_layout = QVBoxLayout()
        self.false_layout.addLayout(self.false_actions_layout)
        false_add = QPushButton("Добавить действие")
        false_add.clicked.connect(lambda: self.add_action("false"))
        self.false_layout.addWidget(false_add)
        branches_layout.addWidget(self.true_group)
        branches_layout.addWidget(self.false_group)
        self.builder_fields_layout.addWidget(self.branches_container)
        self._sync_action_sections()

    def _sync_trigger_page(self) -> None:
        self.trigger_stack.setCurrentIndex(max(0, self.trigger_combo.currentIndex()))

    def _sync_condition_page(self) -> None:
        self.condition_stack.setCurrentIndex(max(0, self.condition_kind_combo.currentIndex()))

    def _sync_action_sections(self) -> None:
        conditional = self.condition_group.isChecked()
        self.linear_group.setVisible(not conditional)
        self.branches_container.setVisible(conditional)

    def _mark_dirty(self, *_args) -> None:
        if self._loading or not self._editable:
            return
        self._dirty = True
        self.save_button.setEnabled(True)
        self.status_label.setText("Есть несохранённые изменения. Нажми «Сохранить».")
        self._update_preview()

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def _render_branch(self, branch: str) -> None:
        layout = {
            "main": self.linear_actions_layout,
            "true": self.true_actions_layout,
            "false": self.false_actions_layout,
        }[branch]
        self._clear_layout(layout)
        actions = self._actions[branch]
        if not actions:
            empty = QLabel("Пока пусто. Добавь первое действие.")
            empty.setObjectName("secondaryText")
            layout.addWidget(empty)
            return
        for index, action in enumerate(actions):
            title, description = self._describe_draft_action(action)
            row = ActionCard(
                title,
                description,
                lambda b=branch, i=index: self.edit_action(b, i),
                lambda b=branch, i=index: self.move_action(b, i, -1),
                lambda b=branch, i=index: self.move_action(b, i, 1),
                lambda b=branch, i=index: self.remove_action(b, i),
                first=index == 0,
                last=index == len(actions) - 1,
            )
            layout.addWidget(row)

    def _render_all_branches(self) -> None:
        for branch in ("main", "true", "false"):
            self._render_branch(branch)

    def _describe_draft_action(self, action: dict[str, Any]) -> tuple[str, str]:
        if action.get("kind") == "wait":
            return "Подождать", f"Пауза {float(action.get('seconds', 1)):g} сек."
        spec = self.registry.get_spec(str(action.get("name", "")))
        if spec is None:
            return "Недоступное действие", "Инструмент больше не зарегистрирован."
        node_kind = "action.repeat" if action.get("kind") == "repeat" else "action.tool"
        node_config = {
            "name": spec.name,
            "arguments": dict(action.get("arguments", {})),
        }
        if node_kind == "action.repeat":
            node_config["count"] = action.get("count", 1)
        node = GraphNode("preview", node_kind, node_config)
        detail = describe_action(node)
        return _friendly_tool_title(spec), detail

    def _draft_from_controls(self) -> dict[str, Any]:
        name = self.name_edit.text().strip()
        trigger_kind = str(self.trigger_combo.currentData())
        if trigger_kind == "text":
            phrases = [
                item.strip()
                for item in self.phrase_edit.text().replace(";", ",").split(",")
                if item.strip()
            ]
            trigger_config = {"phrase": phrases[0]} if len(phrases) == 1 else {"phrases": phrases}
        elif trigger_kind == "schedule":
            days = [number for number, check in self.day_checks.items() if check.isChecked()]
            trigger_config = {
                "time": self.schedule_time.time().toString("HH:mm"),
                "days": days,
            }
        elif trigger_kind == "hotkey":
            trigger_config = {"hotkey": str(self.hotkey_combo.currentData())}
        else:
            trigger_config = {}

        condition = None
        if self.condition_group.isChecked():
            kind = str(self.condition_kind_combo.currentData())
            if kind == "hour":
                condition = {
                    "kind": "hour",
                    "operator": str(self.hour_operator.currentData()),
                    "value": self.hour_value.value(),
                }
            else:
                condition = {
                    "kind": "weekday",
                    "value": int(self.condition_weekday.currentData()),
                }
        return {
            "name": name,
            "trigger_kind": trigger_kind,
            "trigger_config": trigger_config,
            "actions": copy.deepcopy(self._actions["main"]),
            "condition": condition,
            "true_actions": copy.deepcopy(self._actions["true"]),
            "false_actions": copy.deepcopy(self._actions["false"]),
        }

    def _build_current_graph(self) -> WorkflowGraph:
        draft = self._draft_from_controls()
        if not draft["name"]:
            raise ValueError("Укажи название сценария.")
        graph = build_workflow_graph(**draft)
        for node in graph.nodes:
            if node.kind not in {"action.tool", "action.repeat"}:
                continue
            result = self.registry.validate_arguments(
                node.config["name"],
                node.config.get("arguments", {}),
            )
            if not result.ok:
                raise ValueError(result.output)
        return graph

    def _update_preview(self, graph: WorkflowGraph | None = None) -> None:
        if graph is None:
            try:
                graph = self._build_current_graph()
            except (ValueError, TypeError, KeyError):
                return
        positions = {}
        if self._workflow_id:
            try:
                positions = self.workflow_library.load_layout(self._workflow_id)
            except (OSError, ValueError, json.JSONDecodeError):
                positions = {}
        self.graph_view.set_graph(graph, positions)
        self.technical_json.setPlainText(
            json.dumps(graph.to_dict(), ensure_ascii=False, indent=2)
        )

    def _set_draft(self, draft: dict[str, Any]) -> None:
        draft = copy.deepcopy(draft)
        self._loading = True
        self.name_edit.setText(str(draft.get("name") or "Новый сценарий"))
        trigger_kind = str(draft.get("trigger_kind") or "text")
        trigger_index = self.trigger_combo.findData(trigger_kind)
        self.trigger_combo.setCurrentIndex(max(0, trigger_index))
        trigger_config = draft.get("trigger_config") or {}
        if trigger_kind == "text":
            phrases = trigger_config.get("phrases", [trigger_config.get("phrase", "")])
            self.phrase_edit.setText(", ".join(str(item) for item in phrases))
        elif trigger_kind == "schedule":
            time_value = QTime.fromString(str(trigger_config.get("time", "09:00")), "HH:mm")
            self.schedule_time.setTime(time_value if time_value.isValid() else QTime(9, 0))
            days = set(trigger_config.get("days", [1, 2, 3, 4, 5]))
            for number, check in self.day_checks.items():
                check.setChecked(number in days)
        elif trigger_kind == "hotkey":
            hotkey = str(trigger_config.get("hotkey", HOTKEYS[0]))
            index = self.hotkey_combo.findData(hotkey)
            if index < 0:
                self.hotkey_combo.addItem(hotkey, hotkey)
                index = self.hotkey_combo.count() - 1
            self.hotkey_combo.setCurrentIndex(index)

        condition = draft.get("condition")
        self.condition_group.setChecked(condition is not None)
        if condition:
            index = self.condition_kind_combo.findData(condition.get("kind"))
            self.condition_kind_combo.setCurrentIndex(max(0, index))
            if condition.get("kind") == "hour":
                operator_index = self.hour_operator.findData(condition.get("operator", "gte"))
                self.hour_operator.setCurrentIndex(max(0, operator_index))
                self.hour_value.setValue(int(condition.get("value", 22)))
            else:
                weekday_index = self.condition_weekday.findData(condition.get("value", 1))
                self.condition_weekday.setCurrentIndex(max(0, weekday_index))

        self._actions = {
            "main": copy.deepcopy(draft.get("actions") or []),
            "true": copy.deepcopy(draft.get("true_actions") or []),
            "false": copy.deepcopy(draft.get("false_actions") or []),
        }
        self._editable = True
        self.builder_fields.setEnabled(True)
        self.editability_notice.hide()
        self._loading = False
        self._dirty = False
        self.save_button.setEnabled(False)
        self.run_button.setEnabled(bool(self._workflow_id))
        self.delete_button.setEnabled(bool(self._workflow_id))
        self._sync_trigger_page()
        self._sync_condition_page()
        self._sync_action_sections()
        self._render_all_branches()
        self._update_preview()

    def _set_read_only_graph(self, graph: WorkflowGraph, message: str) -> None:
        self._selected_graph = graph
        self._editable = False
        self.builder_fields.setEnabled(False)
        self.editability_notice.setText(message)
        self.editability_notice.show()
        self.save_button.setEnabled(False)
        self.run_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self._update_preview(graph)
        self.detail_tabs.setCurrentIndex(2)
        self.status_label.setText(
            "Сложный сценарий можно редактировать в режиме «Для разработчиков» и запускать."
        )

    def _refresh_library(self, *_args, select_id: str | None = None) -> None:
        query = self.search_edit.text().casefold().strip()
        selected_id = select_id or self._workflow_id
        self.scenario_list.blockSignals(True)
        self.scenario_list.clear()
        try:
            entries = self.workflow_library.list()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.scenario_list.blockSignals(False)
            self.status_label.setText(f"Не удалось прочитать библиотеку: {exc}")
            return
        target_row = -1
        for workflow_id, graph in entries:
            trigger_text = describe_trigger(graph)
            visible_text = f"{graph.name}\n{trigger_text}"
            if query and query not in visible_text.casefold() and query not in workflow_id.casefold():
                continue
            item = QListWidgetItem(visible_text)
            item.setData(Qt.ItemDataRole.UserRole, workflow_id)
            self.scenario_list.addItem(item)
            if workflow_id == selected_id:
                target_row = self.scenario_list.count() - 1
        self.scenario_list.blockSignals(False)
        if target_row >= 0:
            self.scenario_list.setCurrentRow(target_row)
        if not entries:
            self.status_label.setText("Пока нет сценариев. Создай первый или выбери готовый шаблон.")

    def _confirm_discard_changes(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Несохранённые изменения",
            "В сценарии есть несохранённые изменения. Продолжить без сохранения?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _select_library_item(self, workflow_id: str | None) -> None:
        if workflow_id is None:
            self.scenario_list.clearSelection()
            self.scenario_list.setCurrentRow(-1)
            return
        for index in range(self.scenario_list.count()):
            item = self.scenario_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == workflow_id:
                self.scenario_list.setCurrentRow(index)
                return

    def new_scenario(self) -> None:
        if not self._confirm_discard_changes():
            self._select_library_item(self._workflow_id)
            return
        self._workflow_id = None
        self._selected_graph = None
        self._set_draft(_default_draft())
        self._select_library_item(None)
        self.detail_tabs.setCurrentIndex(0)
        self.status_label.setText("Заполни название, выбери способ запуска и добавь действия.")

    def choose_template(self) -> None:
        if not self._confirm_discard_changes():
            return
        dialog = TemplateGalleryDialog(_make_templates(self.allowed_apps), self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_draft:
            self._workflow_id = None
            self._selected_graph = None
            self._set_draft(dialog.selected_draft)
            self._select_library_item(None)
            self.detail_tabs.setCurrentIndex(0)
            self.status_label.setText("Шаблон загружен. Проверь параметры и нажми «Сохранить».")

    def load_selected(self) -> None:
        item = self.scenario_list.currentItem()
        if item is None:
            return
        if not self._confirm_discard_changes():
            self._select_library_item(self._workflow_id)
            return
        workflow_id = str(item.data(Qt.ItemDataRole.UserRole))
        try:
            graph = self.workflow_library.load(workflow_id)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.status_label.setText(f"Не удалось открыть сценарий: {exc}")
            return
        self._workflow_id = workflow_id
        self._selected_graph = graph
        try:
            draft = workflow_to_draft(graph)
        except ValueError as exc:
            self._set_read_only_graph(
                graph,
                f"Этот сценарий содержит расширенную логику: {exc} "
                "Его можно просмотреть и запустить, но простой редактор не будет менять схему.",
            )
            return
        self._set_draft(draft)
        self._selected_graph = graph
        self._dirty = False
        self._update_preview(graph)
        self.detail_tabs.setCurrentIndex(0)
        self.status_label.setText(f"Загружен сценарий «{graph.name}».")

    def add_action(self, branch: str) -> None:
        picker = ActionPickerDialog(self._tool_specs, self)
        if picker.exec() != QDialog.DialogCode.Accepted or not picker.selected_name:
            return
        if picker.selected_name == "__wait__":
            dialog = PauseActionDialog(parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            action = {"kind": "wait", "seconds": dialog.seconds.value()}
        else:
            spec = self.registry.get_spec(picker.selected_name)
            if spec is None:
                self.status_label.setText("Действие больше недоступно в текущей конфигурации.")
                return
            dialog = ToolActionDialog(
                self.registry,
                spec,
                allowed_apps=self.allowed_apps,
                allowed_processes=self.allowed_processes,
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_action is None:
                return
            action = dialog.result_action
        self._actions[branch].append(action)
        self._render_branch(branch)
        self._mark_dirty()
        self._update_preview()

    def edit_action(self, branch: str, index: int) -> None:
        actions = self._actions[branch]
        if not 0 <= index < len(actions):
            return
        current = actions[index]
        if current.get("kind") == "wait":
            dialog = PauseActionDialog(float(current.get("seconds", 1)), self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            updated = {"kind": "wait", "seconds": dialog.seconds.value()}
        else:
            spec = self.registry.get_spec(str(current.get("name", "")))
            if spec is None:
                self.status_label.setText("Действие больше недоступно в текущей конфигурации.")
                return
            dialog = ToolActionDialog(
                self.registry,
                spec,
                initial=current,
                allowed_apps=self.allowed_apps,
                allowed_processes=self.allowed_processes,
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_action is None:
                return
            updated = dialog.result_action
        actions[index] = updated
        self._render_branch(branch)
        self._mark_dirty()
        self._update_preview()

    def move_action(self, branch: str, index: int, offset: int) -> None:
        actions = self._actions[branch]
        next_index = index + offset
        if not (0 <= index < len(actions) and 0 <= next_index < len(actions)):
            return
        actions[index], actions[next_index] = actions[next_index], actions[index]
        self._render_branch(branch)
        self._mark_dirty()
        self._update_preview()

    def remove_action(self, branch: str, index: int) -> None:
        actions = self._actions[branch]
        if not 0 <= index < len(actions):
            return
        actions.pop(index)
        self._render_branch(branch)
        self._mark_dirty()
        self._update_preview()

    def save_current(self) -> bool:
        if not self._editable:
            self.status_label.setText("Этот сложный сценарий доступен только для просмотра и запуска.")
            return False
        try:
            graph = self._build_current_graph()
            workflow_id = self._workflow_id or f"scenario-{uuid.uuid4().hex[:8]}"
            # Keep saved node positions only when editing the same scenario;
            # never carry the previous scenario's layout into a new one.
            positions = (
                self.workflow_library.load_layout(workflow_id)
                if self._workflow_id == workflow_id else {}
            )
            self.graph_view.set_graph(graph, positions)
            self.workflow_library.save(workflow_id, graph)
            self.workflow_library.save_layout(workflow_id, self.graph_view.export_layout())
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.status_label.setText(f"Не удалось сохранить сценарий: {exc}")
            return False
        self._workflow_id = workflow_id
        self._selected_graph = graph
        self._dirty = False
        self.save_button.setEnabled(False)
        self.delete_button.setEnabled(True)
        self.run_button.setEnabled(True)
        self._update_preview(graph)
        self._refresh_library(select_id=workflow_id)
        self.status_label.setText(f"Сценарий «{graph.name}» сохранён на этом компьютере.")
        return True

    def _trigger_values(self, graph: WorkflowGraph) -> tuple[str, str]:
        trigger = next(node for node in graph.nodes if node.kind.startswith("trigger."))
        kind = trigger.kind.removeprefix("trigger.")
        if kind == "text":
            phrases = trigger.config.get("phrases", [trigger.config.get("phrase", "")])
            value = str(phrases[0]) if phrases else ""
        elif kind == "schedule":
            value = str(trigger.config.get("time", ""))
        elif kind == "hotkey":
            value = str(trigger.config.get("hotkey", ""))
        else:
            value = ""
        return kind, value

    def run_current(self) -> None:
        if self._editable:
            if not self.save_current():
                return
            graph = self._selected_graph
        else:
            graph = self._selected_graph
        if graph is None or not self._workflow_id:
            self.status_label.setText("Сначала сохрани сценарий.")
            return
        kind, value = self._trigger_values(graph)
        self.run_requested.emit(self._workflow_id, kind, value)
        self.status_label.setText(f"Сценарий «{graph.name}» передан на запуск.")

    def delete_selected(self) -> None:
        if not self._workflow_id:
            return
        answer = QMessageBox.question(
            self,
            "Удалить сценарий",
            "Удалить выбранный сценарий и его сохранённое расположение блоков?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        workflow_id = self._workflow_id
        try:
            self.workflow_library.delete(workflow_id)
        except OSError as exc:
            self.status_label.setText(f"Не удалось удалить сценарий: {exc}")
            return
        self._workflow_id = None
        self._selected_graph = None
        self._dirty = False
        self._set_draft(_default_draft())
        self._refresh_library()
        self.status_label.setText("Сценарий удалён.")

    def _reset_canvas_layout(self) -> None:
        self.graph_view.reset_layout()
        if self._workflow_id and self._selected_graph:
            try:
                self.workflow_library.save_layout(
                    self._workflow_id,
                    self.graph_view.export_layout(),
                )
            except (OSError, ValueError) as exc:
                self.status_label.setText(f"Не удалось сохранить расположение блоков: {exc}")
                return
        self.status_label.setText("Расположение блоков сброшено.")

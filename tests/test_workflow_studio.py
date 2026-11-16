import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from hellsaiz_pc_ai.app.workflow_studio import (
    ActionPickerDialog,
    ToolActionDialog,
    WorkflowStudioPage,
    _make_templates,
)
from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec
from hellsaiz_pc_ai.workflows.graph import WorkflowGraph
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary
from hellsaiz_pc_ai.workflows.qt_canvas import WorkflowCanvas
from hellsaiz_pc_ai.workflows.studio_model import build_workflow_graph


def _application():
    return QApplication.instance() or QApplication([])


def _registry():
    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="set_volume",
        description="Установить системную громкость Windows.",
        parameters={
            "type": "object",
            "properties": {
                "percent": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "title": "Громкость, %",
                }
            },
            "required": ["percent"],
            "additionalProperties": False,
        },
        risk=RiskLevel.SAFE,
        handler=lambda args: ToolResult(True, f"Громкость {args['percent']}%"),
    ))
    registry.register(ToolSpec(
        name="get_local_time",
        description="Получить текущее время.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk=RiskLevel.SAFE,
        handler=lambda _args: ToolResult(True, "12:00"),
    ))
    return registry


def test_templates_build_only_validated_pc_workflows():
    templates = _make_templates({"notepad": ("notepad.exe",)})

    assert [item["title"] for item in templates] == [
        "Режим «Я дома»",
        "Тихий вечер",
        "Рабочее утро",
        "Игровой режим",
        "Спокойной ночи",
    ]
    for item in templates:
        graph = WorkflowGraph.from_dict(
            __import__(
                "hellsaiz_pc_ai.workflows.studio_model",
                fromlist=["build_workflow_graph"],
            ).build_workflow_graph(**item["draft"]).to_dict()
        )
        assert graph.name == item["draft"]["name"]

    home = next(item for item in templates if item["title"] == "Режим «Я дома»")
    assert "не" in home["description"].casefold()
    assert all(
        node.config.get("name") not in {"turn_on_light", "set_smart_plug", "set_thermostat"}
        for node in WorkflowGraph.from_dict(
            __import__(
                "hellsaiz_pc_ai.workflows.studio_model",
                fromlist=["build_workflow_graph"],
            ).build_workflow_graph(**home["draft"]).to_dict()
        ).nodes
    )


def test_studio_uses_friendly_controls_and_keeps_json_in_developer_mode(tmp_path):
    _application()
    studio = WorkflowStudioPage(
        WorkflowLibrary(tmp_path / "workflows"),
        _registry(),
        allowed_apps={"notepad": ("notepad.exe",)},
    )
    assert studio.name_edit.placeholderText().startswith("Например")
    assert studio.detail_tabs.tabText(0) == "Простой конструктор"
    assert studio.detail_tabs.tabText(1) == "Схема"
    assert studio.detail_tabs.tabText(2) == "Для разработчиков"
    assert not studio.technical_json.isReadOnly()
    assert studio.run_button.isEnabled() is False


def test_studio_builds_and_saves_scenario_without_manual_ids(tmp_path):
    _application()
    library = WorkflowLibrary(tmp_path / "workflows")
    studio = WorkflowStudioPage(
        library,
        _registry(),
        allowed_apps={"notepad": ("notepad.exe",)},
    )
    studio.name_edit.setText("Тихий вечер")
    studio.phrase_edit.setText("тихий вечер, сделай потише")
    studio._actions["main"] = [
        {"kind": "tool", "name": "set_volume", "arguments": {"percent": 25}}
    ]
    graph = studio._build_current_graph()
    assert graph.nodes[0].config["phrases"] == ["тихий вечер", "сделай потише"]
    assert studio.save_current()
    entries = library.list()
    assert len(entries) == 1
    workflow_id, saved_graph = entries[0]
    assert workflow_id.startswith("scenario-")
    assert saved_graph == graph
    assert studio.run_button.isEnabled()


def test_tool_action_dialog_exposes_friendly_field_and_validates():
    _application()
    registry = _registry()
    spec = registry.get_spec("set_volume")
    dialog = ToolActionDialog(registry, spec)
    try:
        assert dialog.windowTitle() == "Изменить громкость"
        assert dialog.fields["percent"].value() == 0
        dialog.fields["percent"].setValue(35)
        dialog._accept_action()
        assert dialog.result_action == {
            "kind": "tool",
            "name": "set_volume",
            "arguments": {"percent": 35},
        }
    finally:
        dialog.close()


def test_repeat_block_keeps_repeat_count_in_simple_editor_round_trip():
    _application()
    registry = _registry()
    library = WorkflowLibrary(__import__("pathlib").Path.cwd() / ".tmp-repeat-test")
    studio = WorkflowStudioPage(library, registry)
    try:
        studio.name_edit.setText("Повтор громкости")
        studio.phrase_edit.setText("повтори громкость")
        studio._actions["main"] = [
            {
                "kind": "repeat",
                "name": "set_volume",
                "arguments": {"percent": 45},
                "count": 3,
            }
        ]
        graph = studio._build_current_graph()
        from hellsaiz_pc_ai.workflows.studio_model import workflow_to_draft

        draft = workflow_to_draft(graph)
        assert draft["actions"][0]["kind"] == "repeat"
        assert draft["actions"][0]["count"] == 3
    finally:
        library.directory.rmdir()



def test_schedule_notepad_scenario_is_built_without_json():
    graph = build_workflow_graph(
        name="Открой блокнот в 22:00",
        trigger_kind="schedule",
        trigger_config={"time": "22:00", "days": [1, 2, 3, 4, 5, 6, 7]},
        actions=[{"kind": "tool", "name": "open_app", "arguments": {"app": "notepad"}}],
    )
    assert graph.name == "Открой блокнот в 22:00"
    assert graph.nodes[0].config["time"] == "22:00"
    assert graph.nodes[1].config == {"name": "open_app", "arguments": {"app": "notepad"}}


def test_legacy_complex_graph_can_be_edited_in_developer_json_mode(tmp_path):
    _application()
    library = WorkflowLibrary(tmp_path / "legacy")
    legacy = WorkflowGraph.from_dict({
        "name": "Старый сценарий",
        "nodes": [
            {"id": "start", "type": "trigger.text", "config": {"phrase": "проверка"}},
            {"id": "hour", "type": "condition.hour", "config": {"operator": "gte", "value": 22}},
            {"id": "weekday", "type": "condition.weekday", "config": {"value": 1}},
            {"id": "night", "type": "action.wait", "config": {"seconds": 1}},
            {"id": "late", "type": "action.wait", "config": {"seconds": 2}},
            {"id": "day", "type": "action.wait", "config": {"seconds": 3}},
        ],
        "edges": [
            {"from": "start", "to": "hour"},
            {"from": "hour", "to": "weekday", "when": "true"},
            {"from": "hour", "to": "day", "when": "false"},
            {"from": "weekday", "to": "night", "when": "true"},
            {"from": "weekday", "to": "late", "when": "false"},
        ],
    })
    library.save("legacy", legacy)
    studio = WorkflowStudioPage(library, _registry())
    studio._refresh_library(select_id="legacy")
    studio.load_selected()
    assert not studio._editable
    assert not studio.technical_json.isReadOnly()
    edited = json.loads(studio.technical_json.toPlainText())
    edited["name"] = "Старый сценарий — исправлен"
    edited["nodes"][-1]["config"]["seconds"] = 4
    studio.technical_json.setPlainText(json.dumps(edited, ensure_ascii=False, indent=2))
    studio._apply_technical_schema()
    saved = library.load("legacy")
    assert saved.name == "Старый сценарий — исправлен"
    assert saved.nodes[-1].config["seconds"] == 4


def test_canvas_uses_friendly_labels_and_emits_double_click():
    _application()
    graph = build_workflow_graph(
        name="Открой блокнот",
        trigger_kind="schedule",
        trigger_config={"time": "22:00", "days": [1, 2, 3, 4, 5, 6, 7]},
        actions=[{"kind": "tool", "name": "open_app", "arguments": {"app": "notepad"}}],
    )
    canvas = WorkflowCanvas()
    canvas.set_graph(graph)
    trigger = canvas._nodes["start"]
    action = canvas._nodes["action_01"]
    assert trigger._summary().startswith("Расписание: 22:00")
    assert action._summary() == "Открыть: Notepad"
    assert trigger._title() == "НАЧАЛО"
    received = []
    canvas.node_double_clicked.connect(received.append)
    trigger.double_clicked.emit("start")
    assert received == ["start"]

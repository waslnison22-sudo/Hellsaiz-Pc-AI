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


def test_studio_uses_friendly_controls_and_no_editable_json():
    _application()
    studio = WorkflowStudioPage(
        WorkflowLibrary(__import__("pathlib").Path.cwd() / ".tmp-scenario-test"),
        _registry(),
        allowed_apps={"notepad": ("notepad.exe",)},
    )
    try:
        assert studio.name_edit.placeholderText().startswith("Например")
        assert studio.detail_tabs.tabText(0) == "Простой конструктор"
        assert studio.detail_tabs.tabText(1) == "Схема"
        assert studio.technical_json.isReadOnly()
        assert studio.run_button.isEnabled() is False
    finally:
        studio.workflow_library.directory.rmdir()


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

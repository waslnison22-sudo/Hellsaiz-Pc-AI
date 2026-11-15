import pytest

from hellsaiz_pc_ai.workflows.graph import WorkflowGraph
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary


def sample_graph():
    return WorkflowGraph.from_dict({
        "name": "Open notepad",
        "nodes": [
            {"id": "start", "type": "trigger.text", "config": {"phrase": "блокнот"}},
            {"id": "open", "type": "action.tool", "config": {"name": "open_app", "arguments": {"app": "notepad"}}},
        ],
        "edges": [{"from": "start", "to": "open"}],
    })


def test_library_saves_loads_and_lists_graphs(tmp_path):
    library = WorkflowLibrary(tmp_path)
    saved = library.save("open-notepad", sample_graph())
    assert saved.exists()
    assert library.load("open-notepad") == sample_graph()
    assert library.list() == [("open-notepad", sample_graph())]


def test_library_rejects_path_traversal(tmp_path):
    library = WorkflowLibrary(tmp_path)
    with pytest.raises(ValueError):
        library.save("../outside", sample_graph())


def test_library_deletes_graph(tmp_path):
    library = WorkflowLibrary(tmp_path)
    library.save("demo", sample_graph())
    library.delete("demo")
    assert library.list() == []


def test_library_persists_visual_node_positions(tmp_path):
    library = WorkflowLibrary(tmp_path)
    library.save("demo", sample_graph())
    positions = {
        "start": {"x": 72.5, "y": 44},
        "open": {"x": 390, "y": 210.25},
    }

    saved = library.save_layout("demo", positions)

    assert saved.is_file()
    assert library.load_layout("demo") == {
        "start": {"x": 72.5, "y": 44.0},
        "open": {"x": 390.0, "y": 210.25},
    }


def test_library_rejects_invalid_visual_layout_coordinates(tmp_path):
    library = WorkflowLibrary(tmp_path)

    with pytest.raises(ValueError, match="out of range"):
        library.save_layout("demo", {"start": {"x": 100001, "y": 0}})

    with pytest.raises(ValueError, match="numeric"):
        library.save_layout("demo", {"start": {"x": True, "y": 0}})


def test_deleting_workflow_also_deletes_its_layout(tmp_path):
    library = WorkflowLibrary(tmp_path)
    library.save("demo", sample_graph())
    library.save_layout("demo", {"start": {"x": 10, "y": 20}})
    library.delete("demo")

    assert library.load_layout("demo") == {}


def test_library_skips_workflows_with_malformed_json_value_types(tmp_path):
    import json

    library = WorkflowLibrary(tmp_path)
    malformed = {
        "name": "Broken workflow",
        "nodes": [
            {"id": "start", "type": [], "config": {}},
            {"id": "end", "type": "action.wait", "config": {"seconds": 0}},
        ],
        "edges": [{"from": "start", "to": "end"}],
    }
    (tmp_path / "broken.json").write_text(json.dumps(malformed), encoding="utf-8")

    assert library.list() == []

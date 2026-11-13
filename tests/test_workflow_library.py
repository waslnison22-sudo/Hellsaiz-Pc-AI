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

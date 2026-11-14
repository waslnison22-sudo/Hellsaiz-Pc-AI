from pathlib import Path

from hellsaiz_pc_ai.core.commands import CommandRouter
from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


def make_router():
    registry = ToolRegistry()
    called = []
    schemas = {
        "list_directory": {"path": {"type": "string"}},
        "search_files": {"path": {"type": "string"}, "query": {"type": "string"}},
        "read_text_file": {"path": {"type": "string"}},
        "open_allowed_path": {"path": {"type": "string"}},
        "create_directory": {"path": {"type": "string"}},
        "write_text_file": {"path": {"type": "string"}, "text": {"type": "string"}},
    }
    required = {
        "list_directory": ["path"],
        "search_files": ["path", "query"],
        "read_text_file": ["path"],
        "open_allowed_path": ["path"],
        "create_directory": ["path"],
        "write_text_file": ["path", "text"],
    }
    for name, properties in schemas.items():
        registry.register(ToolSpec(
            name,
            name,
            {
                "type": "object",
                "properties": properties,
                "required": required[name],
                "additionalProperties": False,
            },
            RiskLevel.CONFIRM,
            lambda args, name=name: called.append((name, args)) or ToolResult(True, name),
        ))
    return CommandRouter(registry, {}, {}, {}), called


def test_file_commands_preserve_paths_and_parameters():
    router, called = make_router()

    router.route("покажи файлы в папке C:/Users/Me/Documents")
    router.route("найди файл report в папке C:/Users/Me/Documents")
    router.route("прочитай файл C:/Users/Me/Documents/notes.txt")
    router.route("открой папку C:/Users/Me/Documents")

    assert called == [
        ("list_directory", {"path": "C:/Users/Me/Documents"}),
        ("search_files", {"query": "report", "path": "C:/Users/Me/Documents"}),
        ("read_text_file", {"path": "C:/Users/Me/Documents/notes.txt"}),
        ("open_allowed_path", {"path": "C:/Users/Me/Documents"}),
    ]


def test_file_creation_commands_extract_literal_content():
    router, called = make_router()

    router.route('создай папку "Новый проект" в папке C:/Users/Me/Documents')
    router.route('создай файл "readme.txt" в папке C:/Users/Me/Documents с текстом Hello, world!')

    assert called == [
        ("create_directory", {"path": str(Path("C:/Users/Me/Documents") / "Новый проект")}),
        (
            "write_text_file",
            {
                "path": str(Path("C:/Users/Me/Documents") / "readme.txt"),
                "text": "Hello, world!",
            },
        ),
    ]

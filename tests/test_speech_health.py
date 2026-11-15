from pathlib import Path
import sqlite3

from hellsaiz_pc_ai.app.health import (
    HealthItem,
    collect_speech_health,
    collect_storage_health,
    summarize_health,
)
from hellsaiz_pc_ai.speech.capture import InputDevice
from hellsaiz_pc_ai.storage.reminders import ReminderStore
from hellsaiz_pc_ai.storage.sqlite_store import ChatStore
from hellsaiz_pc_ai.workflows.graph import WorkflowGraph
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary


def test_health_reports_missing_vosk_and_optional_fallback(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("hellsaiz_pc_ai.app.health._module_available", lambda name: name == "sounddevice")
    monkeypatch.setattr(
        "hellsaiz_pc_ai.speech.capture.list_input_devices",
        lambda: [InputDevice(0, "USB Mic", "WASAPI", 1, 48000)],
    )
    checks = collect_speech_health(
        stt_primary="vosk",
        stt_fallback="whisper.cpp",
        vosk_model_path=tmp_path / "missing-vosk",
        whisper_executable=tmp_path / "whisper-cli.exe",
        whisper_model=tmp_path / "ggml.bin",
        tts_engine="sapi5",
        piper_model_path=None,
        is_windows=False,
    )

    by_component = {item.component: item for item in checks}
    assert by_component["Микрофон"].level == "ok"
    assert by_component["STT / vosk"].level == "error"
    assert by_component["STT / Whisper.cpp"].level == "warning"
    assert by_component["TTS / SAPI5"].level == "warning"


def test_health_reports_installed_local_engines(tmp_path: Path, monkeypatch):
    vosk_model = tmp_path / "vosk"
    vosk_model.mkdir()
    whisper_cli = tmp_path / "whisper-cli.exe"
    whisper_cli.write_bytes(b"fake")
    whisper_model = tmp_path / "ggml.bin"
    whisper_model.write_bytes(b"fake")
    piper_model = tmp_path / "voice.onnx"
    piper_model.write_bytes(b"fake")
    monkeypatch.setattr("hellsaiz_pc_ai.app.health._module_available", lambda _name: True)
    monkeypatch.setattr(
        "hellsaiz_pc_ai.speech.capture.list_input_devices",
        lambda: [
            InputDevice(0, "USB Mic", "WASAPI", 1, 48000)
        ],
    )

    checks = collect_speech_health(
        stt_primary="whisper.cpp",
        stt_fallback="vosk",
        vosk_model_path=vosk_model,
        whisper_executable=whisper_cli,
        whisper_model=whisper_model,
        tts_engine="piper",
        piper_model_path=piper_model,
        is_windows=True,
    )

    assert all(item.level == "ok" for item in checks)

def test_storage_health_checks_sqlite_and_workflows_read_only(tmp_path: Path):
    database = tmp_path / "data folder" / "history.sqlite3"
    ChatStore(database)
    ReminderStore(database)
    workflow_dir = tmp_path / "data folder" / "workflows"
    library = WorkflowLibrary(workflow_dir)
    graph = WorkflowGraph.from_dict({
        "name": "Open notepad",
        "nodes": [
            {"id": "start", "type": "trigger.text", "config": {"phrase": "блокнот"}},
            {"id": "open", "type": "action.tool", "config": {"name": "open_app", "arguments": {"app": "notepad"}}},
        ],
        "edges": [{"from": "start", "to": "open"}],
    })
    library.save("test", graph)

    checks = collect_storage_health(
        database_path=database, workflows_path=workflow_dir, low_disk_warning_bytes=0
    )
    by_component = {item.component: item for item in checks}

    assert by_component["История SQLite"].level == "ok"
    assert by_component["Библиотека сценариев"].level == "ok"
    assert by_component["Пользовательское хранилище"].level == "ok"
    assert ChatStore(database).recent_messages() == []
    ChatStore(database).add_message("user", "после диагностики")
    assert ChatStore(database).recent_messages()[-1]["content"] == "после диагностики"


def test_storage_health_reports_corrupt_database_and_invalid_workflow(tmp_path: Path):
    database = tmp_path / "history.sqlite3"
    database.write_bytes(b"not a sqlite database")
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    (workflow_dir / "broken.json").write_text("{invalid", encoding="utf-8")

    checks = collect_storage_health(database_path=database, workflows_path=workflow_dir)
    by_component = {item.component: item for item in checks}

    assert by_component["История SQLite"].level == "error"
    assert by_component["Библиотека сценариев"].level == "warning"


def test_storage_health_reports_missing_database_and_uninitialized_workflows(tmp_path: Path):
    checks = collect_storage_health(
        database_path=tmp_path / "missing" / "history.sqlite3",
        workflows_path=tmp_path / "missing" / "workflows",
    )
    by_component = {item.component: item for item in checks}

    assert by_component["История SQLite"].level == "error"
    assert by_component["Библиотека сценариев"].level == "warning"
    assert by_component["Пользовательское хранилище"].level == "error"


def test_health_summary_uses_worst_level_and_counts():
    checks = [
        HealthItem("a", "ok", "ok"),
        HealthItem("b", "warning", "warn"),
        HealthItem("c", "error", "error"),
    ]

    level, summary = summarize_health(checks)

    assert level == "error"
    assert summary == "OK: 1 · предупреждения: 1 · ошибки: 1"


def test_empty_health_summary_is_warning():
    level, summary = summarize_health([])

    assert level == "warning"
    assert "не вернула результатов" in summary.casefold()


def test_storage_health_reports_missing_required_sqlite_table(tmp_path: Path):
    database = tmp_path / "partial.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, created_at TEXT, role TEXT, content TEXT)"
        )
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    checks = collect_storage_health(database_path=database, workflows_path=workflow_dir)
    by_component = {item.component: item for item in checks}

    assert by_component["История SQLite"].level == "error"
    assert "reminders" in by_component["История SQLite"].message


def test_storage_health_skips_oversized_workflow_json(tmp_path: Path):
    database = tmp_path / "history.sqlite3"
    ChatStore(database)
    ReminderStore(database)
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    (workflow_dir / "oversized.json").write_text(
        " " * 1_000_001,
        encoding="utf-8",
    )

    checks = collect_storage_health(
        database_path=database,
        workflows_path=workflow_dir,
        low_disk_warning_bytes=0,
    )
    by_component = {item.component: item for item in checks}

    assert by_component["Библиотека сценариев"].level == "warning"
    assert "oversized.json" in by_component["Библиотека сценариев"].message


def test_storage_health_handles_excessively_nested_workflow_json(tmp_path: Path):
    database = tmp_path / "history.sqlite3"
    ChatStore(database)
    ReminderStore(database)
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    (workflow_dir / "deep.json").write_text(
        "[" * 1500 + "0" + "]" * 1500,
        encoding="utf-8",
    )

    checks = collect_storage_health(
        database_path=database,
        workflows_path=workflow_dir,
        low_disk_warning_bytes=0,
    )
    by_component = {item.component: item for item in checks}

    assert by_component["История SQLite"].level == "ok"
    assert by_component["Библиотека сценариев"].level == "warning"
    assert "deep.json" in by_component["Библиотека сценариев"].message


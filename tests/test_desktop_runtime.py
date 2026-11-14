from __future__ import annotations

from pathlib import Path

from hellsaiz_pc_ai.app.desktop import build_runtime
from hellsaiz_pc_ai.config import LLMSettings, Settings


def test_runtime_works_without_any_ai_provider(tmp_path: Path):
    settings = Settings(
        llm=LLMSettings(enabled=False),
        allow_remote_llm=False,
        database_path=tmp_path / "history.sqlite3",
        workflows_path=tmp_path / "workflows",
    )

    (
        router,
        assistant,
        store,
        workflow_library,
        workflow_runner,
        registry,
        reminder_store,
        allowed_apps,
        profile_data,
        file_access_settings,
        vision_settings,
    ) = build_runtime(settings)

    assert assistant is None
    assert "без ИИ" in router.route("помощь")
    assert router.route("который час").startswith("Готово.")
    assert registry.get_spec("open_app") is not None
    assert registry.get_spec("create_reminder") is not None
    assert registry.get_spec("list_directory") is not None
    assert registry.get_spec("read_screen_text") is not None
    assert vision_settings["ocr_enabled"] is False
    assert file_access_settings.allow_writes is False
    assert allowed_apps
    assert store is not None
    assert workflow_library is not None
    assert workflow_runner is not None
    assert reminder_store is not None

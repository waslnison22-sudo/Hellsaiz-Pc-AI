from __future__ import annotations

from pathlib import Path

from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.tools import file_system


def test_path_resolution_rejects_escape_and_symlink_escape(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = allowed / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        return

    assert file_system.resolve_allowed_path(str(allowed / "safe.txt"), [allowed]) == allowed / "safe.txt"
    for path in ("../outside/secret.txt", str(outside / "secret.txt"), str(link / "secret.txt")):
        try:
            file_system.resolve_allowed_path(path, [allowed], must_exist=Path(path).exists())
        except file_system.FileAccessError:
            pass
        else:
            raise AssertionError(f"Out-of-root path was accepted: {path}")


def test_list_search_and_read_are_scoped(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "notes.txt").write_text("Hellsaiz local assistant", encoding="utf-8")
    (allowed / "docs").mkdir()
    (allowed / "docs" / "plan.md").write_text("Milestone one", encoding="utf-8")

    listing = file_system._list_directory(str(allowed), [allowed])
    search = file_system._search_files(str(allowed), "plan", [allowed])
    read = file_system._read_text_file(str(allowed / "notes.txt"), [allowed])

    assert listing.ok and "notes.txt" in listing.output
    assert search.ok and "plan.md" in search.output
    assert read.ok and "Hellsaiz local assistant" in read.output


def test_read_rejects_binary_large_and_unsupported_files(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    binary = root / "image.png"
    binary.write_bytes(b"\x89PNG")
    large = root / "large.txt"
    large.write_bytes(b"x" * (file_system.MAX_READ_BYTES + 1))

    assert not file_system._read_text_file(str(binary), [root]).ok
    assert not file_system._read_text_file(str(large), [root]).ok


def test_open_path_blocks_executable_extensions_and_supports_allowed_files(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    executable = root / "payload.exe"
    executable.write_bytes(b"not really executable")
    document = root / "notes.txt"
    document.write_text("safe", encoding="utf-8")
    opened = []

    blocked = file_system._open_path(str(executable), [root], opener=opened.append)
    result = file_system._open_path(str(document), [root], opener=opened.append)

    assert not blocked.ok
    assert result.ok
    assert opened == [str(document)]


def test_write_operations_are_disabled_by_default_and_never_overwrite(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    existing = root / "existing.txt"
    existing.write_text("original", encoding="utf-8")

    denied = file_system._write_text_file(
        str(root / "new.txt"), "hello", [root], allow_writes=False
    )
    duplicate = file_system._write_text_file(
        str(existing), "replacement", [root], allow_writes=True
    )
    created = file_system._write_text_file(
        str(root / "new.txt"), "hello", [root], allow_writes=True
    )

    assert not denied.ok
    assert not duplicate.ok
    assert existing.read_text(encoding="utf-8") == "original"
    assert created.ok
    assert (root / "new.txt").read_text(encoding="utf-8") == "hello"


def test_registry_uses_dynamic_write_permission_and_roots(tmp_path: Path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    state = {"roots": [root_a], "writes": False}
    registry = ToolRegistry()
    file_system.register_file_system_tools(
        registry,
        lambda: tuple(state["roots"]),
        allow_writes=lambda: state["writes"],
    )

    denied = registry.execute(
        "write_text_file", {"path": str(root_a / "first.txt"), "text": "first"}
    )
    state["roots"] = [root_b]
    state["writes"] = True
    wrong_root = registry.execute(
        "write_text_file", {"path": str(root_a / "second.txt"), "text": "second"}
    )
    allowed = registry.execute(
        "write_text_file", {"path": str(root_b / "second.txt"), "text": "second"}
    )

    assert not denied.ok
    assert not wrong_root.ok
    assert allowed.ok


def test_file_access_settings_persist_and_reject_drive_root(tmp_path: Path):
    from hellsaiz_pc_ai.app.file_access import (
        FileAccessSettings,
        load_file_access_settings,
        save_file_access_settings,
    )

    root = tmp_path / "personal"
    root.mkdir()
    path = tmp_path / "config" / "file_access.json"
    state = FileAccessSettings([root], True)
    save_file_access_settings(path, state)

    loaded = load_file_access_settings(path)
    assert loaded.roots == [root.resolve()]
    assert loaded.allow_writes

    drive_root = Path(Path.home().anchor)
    try:
        save_file_access_settings(path, FileAccessSettings([drive_root], False))
    except ValueError as exc:
        assert "корень диска" in str(exc).casefold()
    else:
        raise AssertionError("Drive root must never be accepted as a file-access root")

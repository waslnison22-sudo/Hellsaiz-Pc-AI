import json

from hellsaiz_pc_ai.app_catalog import (
    AppCandidate,
    add_candidate,
    catalog_mappings,
    load_user_catalog,
)


def test_catalog_round_trip_and_aliases(tmp_path):
    executable = tmp_path / "ExampleApp.exe"
    executable.write_bytes(b"test")
    catalog_path = tmp_path / "apps.json"

    entry = add_candidate(catalog_path, AppCandidate("Example App", executable))
    items = load_user_catalog(catalog_path)
    allowed, aliases = catalog_mappings(items)

    assert entry["key"] == "example-app"
    assert allowed["example-app"] == (str(executable.resolve()),)
    assert aliases["example-app"] == ("Example App", "ExampleApp")


def test_duplicate_path_is_not_added_twice(tmp_path):
    executable = tmp_path / "portable.exe"
    executable.write_bytes(b"test")
    catalog_path = tmp_path / "apps.json"

    first = add_candidate(catalog_path, AppCandidate("Portable", executable))
    second = add_candidate(catalog_path, AppCandidate("Portable renamed", executable))

    assert first == second
    assert len(load_user_catalog(catalog_path)) == 1


def test_invalid_catalog_is_rejected(tmp_path):
    catalog_path = tmp_path / "apps.json"
    catalog_path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")

    try:
        load_user_catalog(catalog_path)
    except ValueError as exc:
        assert "формат" in str(exc)
    else:
        raise AssertionError("invalid schema should fail")


def test_shortcut_command_is_explicit(tmp_path):
    shortcut = tmp_path / "Example.lnk"
    shortcut.write_bytes(b"shortcut")
    catalog_path = tmp_path / "apps.json"
    entry = add_candidate(catalog_path, AppCandidate("Example", shortcut, "shortcut"))
    allowed, _ = catalog_mappings(load_user_catalog(catalog_path))

    assert entry["launch_kind"] == "shortcut"
    assert allowed["example"] == ("__shell_link__", str(shortcut.resolve()))

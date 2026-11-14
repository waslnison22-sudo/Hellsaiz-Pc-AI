import json
from pathlib import Path

import pytest

from hellsaiz_pc_ai.launcher import resolve_active_target


def make_installation(root: Path, version: str = "0.1.4") -> Path:
    version_dir = root / "versions" / version
    version_dir.mkdir(parents=True)
    (version_dir / "HellsaizPC_AI.exe").write_bytes(b"test exe")
    (root / "active.json").write_text(
        json.dumps({"schema_version": 1, "active_version": version}),
        encoding="utf-8",
    )
    return root


def test_launcher_resolves_active_version(tmp_path):
    root = make_installation(tmp_path)

    target = resolve_active_target(root)

    assert target == (root / "versions" / "0.1.4" / "HellsaizPC_AI.exe").resolve()


@pytest.mark.parametrize("version", ["../outside", "..", "nested/0.1.4", "nested\\0.1.4", ""])
def test_launcher_rejects_path_traversal_versions(tmp_path, version):
    root = tmp_path / "install"
    root.mkdir()
    (root / "active.json").write_text(
        json.dumps({"schema_version": 1, "active_version": version}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="недопустимая версия"):
        resolve_active_target(root)


def test_launcher_rejects_unsupported_active_schema(tmp_path):
    root = tmp_path / "install"
    root.mkdir()
    (root / "active.json").write_text(
        json.dumps({"schema_version": 99, "active_version": "0.1.4"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="неподдерживаемую схему"):
        resolve_active_target(root)


def test_launcher_rejects_missing_version_executable(tmp_path):
    root = tmp_path / "install"
    (root / "versions" / "0.1.4").mkdir(parents=True)
    (root / "active.json").write_text(
        json.dumps({"schema_version": 1, "active_version": "0.1.4"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="не найдены"):
        resolve_active_target(root)

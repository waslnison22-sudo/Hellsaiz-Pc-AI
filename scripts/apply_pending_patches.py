"""Применяет ожидающие патчи из docs/patches перед тестами и сборкой.

Конвейер: изменения desktop.py и других больших файлов доставляются в репозиторий
как патчи (docs/patches/*.patch), а этот скрипт применяет их в рабочей копии перед
прогоном тестов и сборкой пакета. Идемпотентно: уже применённый патч пропускается.

Патчи хранятся в zero-context формате (n=0): только строки удаления и добавления,
без контекстных строк. Такой формат устойчив к потере невидимых пробелов при
ручной вставке, но git apply принимает его только с флагом --unidiff-zero.

Выход: 0 — все патчи применены или пропущены; 1 — какой-то патч не применился.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path





def _workflow_state_path() -> Path | None:
    """Return a per-run state file so repeated CI invocations stay idempotent.

    Later patches can legitimately remove context lines used by earlier
    zero-context patches. A content-hash record avoids trying to reverse-apply
    an earlier patch at stale line offsets on the second invocation.
    """
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not run_id:
        return None
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    workspace = str(Path.cwd().resolve())
    workspace_key = hashlib.sha256(workspace.encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / (
        f"hellsaiz-patches-{run_id}-{attempt}-{workspace_key}.json"
    )


def _load_workflow_state(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(name): str(digest)
        for name, digest in payload.items()
        if isinstance(name, str) and isinstance(digest, str)
    }


def _save_workflow_state(path: Path | None, state: dict[str, str]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as exc:
        print(f"WARNING: не удалось сохранить состояние патчей: {exc}")


def main() -> int:
    # GitHub's Windows runner may use cp1252 for stdout. Patch status messages
    # contain Russian text, so force UTF-8 before printing or the second,
    # idempotent invocation can fail after all patches were already applied.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")

    patch_dir = Path("docs/patches")
    if not patch_dir.is_dir():
        print("docs/patches отсутствует — патчей нет.")
        return 0
    failures = 0
    state_path = _workflow_state_path()
    applied_state = _load_workflow_state(state_path)
    for patch in sorted(patch_dir.glob("*.patch")):
        patch_hash = hashlib.sha256(patch.read_bytes()).hexdigest()
        if applied_state.get(patch.name) == patch_hash:
            print(f"SKIP (уже применён в этом workflow run): {patch.name}")
            continue
        reverse_check = subprocess.run(
            ["git", "apply", "--reverse", "--check", "--unidiff-zero", str(patch)],
            capture_output=True,
            text=True,
        )
        if reverse_check.returncode == 0:
            print(f"SKIP (уже применён): {patch.name}")
            applied_state[patch.name] = patch_hash
            _save_workflow_state(state_path, applied_state)
            continue
        result = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "--unidiff-zero", str(patch)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            failures += 1
            print(f"FAILED: {patch.name}")
            print(result.stdout)
            print(result.stderr)
            continue
        print(f"APPLIED: {patch.name}")
        applied_state[patch.name] = patch_hash
        _save_workflow_state(state_path, applied_state)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

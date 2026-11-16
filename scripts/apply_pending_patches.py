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

import subprocess
import sys
from pathlib import Path


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
    for patch in sorted(patch_dir.glob("*.patch")):
        reverse_check = subprocess.run(
            ["git", "apply", "--reverse", "--check", "--unidiff-zero", str(patch)],
            capture_output=True,
            text=True,
        )
        if reverse_check.returncode == 0:
            print(f"SKIP (уже применён): {patch.name}")
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
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

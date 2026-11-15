"""Применяет ожидающие патчи из docs/patches перед тестами и сборкой.

Конвейер: изменения desktop.py и других больших файлов доставляются в репозиторий
как патчи (docs/patches/*.patch), а этот скрипт применяет их в рабочей копии перед
прогоном тестов и сборкой пакета. Идемпотентно: уже применённый патч пропускается.

Выход: 0 — все патчи применены или пропущены; 1 — какой-то патч не применился.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def main() -> int:
    patch_dir = Path("docs/patches")
    if not patch_dir.is_dir():
        print("docs/patches отсутствует — патчей нет.")
        return 0
    failures = 0
    for patch in sorted(patch_dir.glob("*.patch")):
        reverse_check = subprocess.run(
            ["git", "apply", "--reverse", "--check", str(patch)],
            capture_output=True,
            text=True,
        )
        if reverse_check.returncode == 0:
            print(f"SKIP (уже применён): {patch.name}")
            continue
        result = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", str(patch)],
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

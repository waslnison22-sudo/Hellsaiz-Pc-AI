from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        import yaml
    except ImportError:
        print("PyYAML is not installed; install with python -m pip install pyyaml")
        return 2
    for raw in sys.argv[1:]:
        path = Path(raw)
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"INVALID {path}: {type(exc).__name__}: {exc}")
            return 1
        if not isinstance(document, dict) or not isinstance(document.get("jobs"), dict):
            print(f"INVALID {path}: expected top-level workflow jobs mapping")
            return 1
        print(f"VALID {path}: {len(document['jobs'])} jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

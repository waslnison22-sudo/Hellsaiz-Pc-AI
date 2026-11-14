from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/set_version.py X.Y.Z")
    version = sys.argv[1].removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Version must be a stable semantic version such as 1.2.3.")
    target = Path(__file__).resolve().parents[1] / "src" / "hellsaiz_pc_ai" / "version.py"
    target.write_text(
        '"""Version embedded into Windows builds; release workflow rewrites this file before packaging."""\n\n'
        f'APP_VERSION = "{version}"\n',
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

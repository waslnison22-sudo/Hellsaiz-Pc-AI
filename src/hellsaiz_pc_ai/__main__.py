from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        from hellsaiz_pc_ai.app.package_smoke import check_packaged_runtime

        log_path = Path(tempfile.gettempdir()) / "HellsaizPC_AI-package-self-test.log"
        try:
            with log_path.open("w", encoding="utf-8") as log:
                def report(message: str) -> None:
                    log.write(message + "\n")
                    log.flush()

                report("Hellsaiz PC AI packaged runtime self-test started.")
                failures = check_packaged_runtime(progress=report)
                if failures:
                    for module_name, detail in failures:
                        report(f"PACKAGE SELF-TEST FAILED: {module_name}: {detail}")
                    return 2
                report("All packaged runtime modules imported successfully.")
                return 0
        except OSError:
            failures = check_packaged_runtime()
            return 2 if failures else 0

    from hellsaiz_pc_ai.app.desktop import main as desktop_main

    return desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())

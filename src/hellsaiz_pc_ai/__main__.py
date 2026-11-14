from __future__ import annotations

import sys


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        from hellsaiz_pc_ai.app.package_smoke import check_packaged_runtime

        failures = check_packaged_runtime()
        if failures:
            for module_name, detail in failures:
                sys.stderr.write(f"PACKAGE SELF-TEST FAILED: {module_name}: {detail}\\n")
            return 2
        return 0

    from hellsaiz_pc_ai.app.desktop import main as desktop_main

    return desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())

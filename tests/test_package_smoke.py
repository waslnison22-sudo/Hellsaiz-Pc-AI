from hellsaiz_pc_ai.app.package_smoke import (
    PACKAGED_RUNTIME_MODULES,
    check_packaged_runtime,
)


def test_package_smoke_imports_every_required_module():
    imported = []

    def fake_importer(name):
        imported.append(name)
        return object()

    assert check_packaged_runtime(fake_importer) == []
    assert tuple(imported) == PACKAGED_RUNTIME_MODULES


def test_package_smoke_reports_all_missing_or_broken_modules():
    def broken_importer(name):
        if name in {"sounddevice", "piper"}:
            raise ImportError(f"missing {name}")
        if name == "onnxruntime":
            raise OSError("DLL load failed")
        return object()

    failures = check_packaged_runtime(broken_importer)

    assert [name for name, _ in failures] == ["sounddevice", "piper", "onnxruntime"]

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from hellsaiz_pc_ai.tools import ocr_models, screen_ocr


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body
        self.offset = 0
        self.headers = {"Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        if size < 0:
            size = len(self.body)
        chunk = self.body[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


def test_model_status_reports_missing_models(tmp_path: Path):
    status = ocr_models.check_russian_ocr_models(tmp_path)
    assert not status.ready
    assert set(status.missing) == {"det", "cls", "rec"}
    assert status.invalid == ()


def test_download_verifies_hash_and_installs_all_models(tmp_path: Path, monkeypatch):
    bodies = {
        key: f"fake-{key}-model".encode("ascii")
        for key in ("det", "cls", "rec")
    }
    metadata = {}
    for key, item in ocr_models.RUSSIAN_OCR_MODELS.items():
        body = bodies[key]
        metadata[key] = {
            **item,
            "sha256": hashlib.sha256(body).hexdigest(),
            "filename": item["filename"],
        }
    monkeypatch.setattr(ocr_models, "RUSSIAN_OCR_MODELS", metadata)
    requested = []

    def opener(request, timeout):
        requested.append((request.full_url, timeout))
        key = next(name for name, item in metadata.items() if request.full_url == item["url"])
        return FakeResponse(bodies[key])

    statuses = []
    result = ocr_models.download_russian_ocr_models(
        tmp_path,
        opener=opener,
        progress=lambda key, state: statuses.append((key, state)),
    )

    assert result.ready
    assert set(statuses) == {("det", "downloaded"), ("cls", "downloaded"), ("rec", "downloaded")}
    for key in bodies:
        assert ocr_models.model_path(tmp_path, key).read_bytes() == bodies[key]
        assert not ocr_models.model_path(tmp_path, key).with_suffix(".onnx.download").exists()
    assert len(requested) == 3
    assert all(timeout == ocr_models.DOWNLOAD_TIMEOUT_SECONDS for _url, timeout in requested)


def test_download_rejects_checksum_mismatch_and_removes_partial_file(tmp_path: Path, monkeypatch):
    metadata = {
        **ocr_models.RUSSIAN_OCR_MODELS["det"],
        "sha256": "0" * 64,
    }
    monkeypatch.setattr(
        ocr_models,
        "RUSSIAN_OCR_MODELS",
        {"det": metadata},
    )
    target = ocr_models.model_path(tmp_path, "det")

    with pytest.raises(ocr_models.OcrModelError, match="SHA-256"):
        ocr_models.download_russian_ocr_models(
            tmp_path,
            opener=lambda *_args, **_kwargs: FakeResponse(b"wrong model"),
        )

    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".download").exists()


def test_ocr_refuses_to_capture_screen_when_models_are_missing(monkeypatch):
    captured = []
    output = screen_ocr.read_primary_screen_text(
        capture=lambda: captured.append(True),
        engine_factory=lambda: (_ for _ in ()).throw(
            ocr_models.OcrModelError("models missing")
        ),
    )
    assert not output.ok
    assert captured == []


def test_engine_uses_cyrillic_recognition_and_cpu_onnx(monkeypatch, tmp_path: Path):
    captured = {}
    class FakeRapidOCR:
        def __init__(self, params):
            captured.update(params)

    monkeypatch.setattr(
        screen_ocr,
        "check_russian_ocr_models",
        lambda _root: ocr_models.OcrModelsStatus(True, (), ()),
    )
    monkeypatch.setattr(
        screen_ocr,
        "model_path",
        lambda root, key: Path(root) / f"{key}.onnx",
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "rapidocr",
        SimpleNamespace(RapidOCR=FakeRapidOCR),
    )
    monkeypatch.setattr(screen_ocr, "_engine", None)

    engine = screen_ocr._get_engine(tmp_path)

    assert isinstance(engine, FakeRapidOCR)
    assert captured["Rec.lang_type"] == "cyrillic"
    assert captured["Rec.ocr_version"] == "PP-OCRv5"
    assert captured["Det.lang_type"] == "multi"
    assert captured["Cls.lang_type"] == "multi"
    assert all(value == "onnxruntime" for key, value in captured.items() if key.endswith(".engine_type"))


def test_model_download_limits_timeout(tmp_path: Path):
    with pytest.raises(ValueError, match="от 5 до 300"):
        ocr_models.download_russian_ocr_models(tmp_path, timeout_seconds=301)


def test_official_model_manifest_paths_and_hashes_are_stable():
    expected = {
        "det": (
            "ch_PP-OCRv5_det_mobile.onnx",
            "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
        ),
        "cls": (
            "ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
            "54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7",
        ),
        "rec": (
            "cyrillic_PP-OCRv5_rec_mobile.onnx",
            "90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711",
        ),
    }
    for key, (filename, sha256) in expected.items():
        item = ocr_models.RUSSIAN_OCR_MODELS[key]
        assert item["filename"] == filename
        assert item["sha256"] == sha256
        assert item["url"].startswith("https://www.modelscope.cn/models/RapidAI/RapidOCR/")

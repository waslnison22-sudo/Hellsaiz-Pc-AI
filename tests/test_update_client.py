import pytest

from hellsaiz_pc_ai.update_client import _version_parts


def test_versions_compare_numerically():
    assert _version_parts("v0.10.0") > _version_parts("0.9.9")
    assert _version_parts("0.2.0") > _version_parts("0.2.0-beta")


def test_latest_release_without_signed_manifest_is_reported_as_incomplete(monkeypatch):
    import json
    import urllib.request

    from hellsaiz_pc_ai.update_client import UpdateCheckError, check_latest_release

    payload = json.dumps({
        "tag_name": "v0.1.4",
        "html_url": "https://github.com/waslnison22-sudo/Hellsaiz-Pc-AI/releases/tag/v0.1.4",
        "published_at": "2026-11-15T07:46:39Z",
        "assets": [],
    }).encode("utf-8")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit=-1):
            return payload

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    class FakeOpener:
        def open(self, *_a, **_k):
            return FakeResponse()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_a, **_k: FakeOpener())

    with pytest.raises(UpdateCheckError, match="Релиз не содержит подписанный update-манифест"):
        check_latest_release("0.1.3", access_token="test-token")


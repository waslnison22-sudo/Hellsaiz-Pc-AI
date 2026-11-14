from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from hellsaiz_pc_ai.network import v2raytun


class FakeResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return b""


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        if self.error:
            raise self.error
        return self.response


def test_proxy_url_is_loopback_only():
    assert v2raytun.validate_proxy_url("http://127.0.0.1:10809") == "http://127.0.0.1:10809"
    with pytest.raises(ValueError):
        v2raytun.validate_proxy_url("http://proxy.example:10809")
    with pytest.raises(ValueError):
        v2raytun.validate_proxy_url("socks5://127.0.0.1:1080")
    with pytest.raises(ValueError):
        v2raytun.validate_proxy_url("http://user:pass@127.0.0.1:10809")


def test_health_check_uses_only_configured_proxy(monkeypatch):
    opener = FakeOpener(response=FakeResponse())
    captured = {}

    def factory(handler):
        captured["handler"] = handler
        return opener

    health = v2raytun.check_http_proxy(
        "http://127.0.0.1:10809",
        "https://api.telegram.org/",
        opener_factory=factory,
    )

    assert health.ok
    assert health.status_code == 204
    assert opener.timeout == 6.0
    assert opener.request.full_url == "https://api.telegram.org/"
    assert "handler" in captured


def test_http_client_error_still_proves_proxy_connectivity():
    opener = FakeOpener(error=HTTPError("https://api.telegram.org/", 404, "not found", {}, io.BytesIO()))
    health = v2raytun.check_http_proxy(
        "http://127.0.0.1:10809",
        "https://api.telegram.org/",
        opener_factory=lambda _handler: opener,
    )
    assert health.ok
    assert health.status_code == 404


def test_proxy_failure_blocks_required_telegram_route():
    status = v2raytun.build_network_status(
        "C:/apps/v2raytun.exe",
        "http://127.0.0.1:10809",
        "https://api.telegram.org/",
        require_proxy=True,
        check_process=lambda: True,
        proxy_checker=lambda *_args: v2raytun.ProxyHealth(
            False, "http://127.0.0.1:10809", "https://api.telegram.org/", 100, None, "offline"
        ),
    )
    assert status.process_running
    assert not status.telegram_ready


def test_direct_network_is_allowed_only_when_proxy_requirement_disabled():
    status = v2raytun.build_network_status(
        "",
        "",
        "https://api.telegram.org/",
        require_proxy=False,
        check_process=lambda: False,
    )
    assert status.telegram_ready
    assert not status.proxy_configured


def test_network_settings_validate_and_persist(tmp_path: Path):
    path = tmp_path / "network.json"
    config = {
        "executable_path": "C:/Program Files/v2RayTun/v2RayTun.exe",
        "proxy_url": "http://127.0.0.1:10809",
        "health_url": "https://api.telegram.org/",
        "require_proxy_for_telegram": True,
        "launch_on_start": True,
    }
    v2raytun.save_network_settings(path, config)
    loaded = v2raytun.load_network_settings(path)
    assert loaded["proxy_url"] == config["proxy_url"]
    assert loaded["require_proxy_for_telegram"] is True
    assert loaded["launch_on_start"] is True

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["proxy_url"] = "http://external.example:10809"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        v2raytun.load_network_settings(path)


def test_launch_client_uses_shell_false_and_no_undocumented_arguments(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(v2raytun.sys, "platform", "win32")
    executable = tmp_path / "v2RayTun.exe"
    executable.write_bytes(b"exe")
    calls = []

    def popen(args, **kwargs):
        calls.append((args, kwargs))
        return object()

    v2raytun.launch_v2raytun(executable, popen=popen)
    assert calls[0][0] == [str(executable.resolve())]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["cwd"] == str(tmp_path.resolve())

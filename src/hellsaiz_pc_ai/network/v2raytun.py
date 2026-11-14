from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener


DEFAULT_HEALTH_URL = "https://api.telegram.org/"
MAX_HEALTH_RESPONSE = 128 * 1024


class NetworkDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProxyHealth:
    ok: bool
    proxy_url: str
    health_url: str
    latency_ms: int
    status_code: int | None
    detail: str


@dataclass(frozen=True)
class V2RayTunStatus:
    executable_configured: bool
    executable_exists: bool
    process_running: bool
    proxy_configured: bool
    proxy_healthy: bool
    telegram_ready: bool
    detail: str


def validate_proxy_url(value: str) -> str:
    raw = value.strip()
    parsed = urlparse(raw)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port is None
        or not 1 <= parsed.port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError(
            "Прокси должен быть локальным HTTP endpoint, например http://127.0.0.1:10809."
        )
    return f"http://{parsed.hostname}:{parsed.port}"


def validate_health_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("URL проверки должен быть корректным HTTPS адресом.")
    return value.strip()


def validate_executable_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.suffix.casefold() != ".exe":
        raise ValueError("Выбранный клиент должен быть существующим Windows EXE.")
    return path


def detect_v2raytun_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import psutil
    except ImportError:
        raise NetworkDependencyError("Для проверки процессов нужен пакет psutil.")
    for process in psutil.process_iter(["name"]):
        try:
            name = str(process.info.get("name") or "").casefold()
            if "v2raytun" in name:
                return True
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return False


def launch_v2raytun(
    executable_path: str | Path,
    *,
    popen: Any = subprocess.Popen,
) -> Any:
    if os.name != "nt":
        raise NetworkDependencyError("Запуск v2RayTun поддерживается только в Windows.")
    path = validate_executable_path(str(executable_path))
    try:
        return popen(
            [str(path)],
            cwd=str(path.parent),
            shell=False,
            close_fds=True,
        )
    except OSError as exc:
        raise NetworkDependencyError(f"Не удалось запустить выбранный клиент ({type(exc).__name__}).") from exc


def check_http_proxy(
    proxy_url: str,
    health_url: str = DEFAULT_HEALTH_URL,
    *,
    timeout_seconds: float = 6.0,
    opener_factory: Any = build_opener,
) -> ProxyHealth:
    proxy = validate_proxy_url(proxy_url)
    endpoint = validate_health_url(health_url)
    if not 1.0 <= timeout_seconds <= 20.0:
        raise ValueError("Тайм-аут проверки должен быть от 1 до 20 секунд.")
    opener = opener_factory(ProxyHandler({"http": proxy, "https": proxy}))
    request = Request(
        endpoint,
        headers={"User-Agent": "HellsaizPC_AI-NetworkCheck/1.0", "Accept": "*/*"},
        method="GET",
    )
    started = time.monotonic()
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", 200))
            response.read(MAX_HEALTH_RESPONSE)
        latency = round((time.monotonic() - started) * 1000)
        if 200 <= status < 500:
            return ProxyHealth(True, proxy, endpoint, latency, status, "HTTPS endpoint reached through the configured proxy.")
        return ProxyHealth(False, proxy, endpoint, latency, status, f"Endpoint returned HTTP {status}.")
    except HTTPError as exc:
        latency = round((time.monotonic() - started) * 1000)
        # 401/403/404 still prove that the proxy tunnel reached the HTTPS host.
        ok = 400 <= exc.code < 500 and exc.code != 407
        return ProxyHealth(
            ok, proxy, endpoint, latency, exc.code,
            "HTTPS endpoint reached; it returned an HTTP client status."
            if ok else f"Proxy/network check failed with HTTP {exc.code}.",
        )
    except (URLError, TimeoutError, OSError) as exc:
        latency = round((time.monotonic() - started) * 1000)
        return ProxyHealth(
            False, proxy, endpoint, latency, None,
            f"Прокси не подтвердил сетевой доступ ({type(exc).__name__}).",
        )


def build_network_status(
    executable_path: str,
    proxy_url: str,
    health_url: str,
    *,
    require_proxy: bool,
    check_process: Any = detect_v2raytun_running,
    proxy_checker: Any = check_http_proxy,
) -> V2RayTunStatus:
    executable_configured = bool(executable_path.strip())
    executable_exists = False
    if executable_configured:
        try:
            executable_exists = validate_executable_path(executable_path).is_file()
        except ValueError:
            executable_exists = False
    try:
        running = bool(check_process())
    except NetworkDependencyError:
        running = False
    proxy_configured = bool(proxy_url.strip())
    health = None
    if proxy_configured:
        try:
            health = proxy_checker(proxy_url, health_url or DEFAULT_HEALTH_URL)
        except (ValueError, NetworkDependencyError):
            health = None
    proxy_healthy = bool(health and health.ok)
    telegram_ready = proxy_healthy if require_proxy else True
    details = []
    if not executable_configured:
        details.append("Путь v2RayTun не выбран.")
    elif not executable_exists:
        details.append("Выбранный EXE не найден.")
    elif not running:
        details.append("Клиент найден, но не запущен.")
    else:
        details.append("Клиент v2RayTun запущен.")
    if not proxy_configured:
        details.append("Локальный HTTP-прокси не настроен.")
    elif proxy_healthy:
        details.append(f"Прокси доступен ({health.latency_ms} мс).")
    else:
        details.append("Прокси не подтвердил доступ к HTTPS endpoint.")
    if telegram_ready:
        details.append("Сетевой шлюз Telegram разрешён.")
    else:
        details.append("Telegram заблокирован до успешной проверки прокси.")
    return V2RayTunStatus(
        executable_configured,
        executable_exists,
        running,
        proxy_configured,
        proxy_healthy,
        telegram_ready,
        " ".join(details),
    )


def load_network_settings(path: Path) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "schema_version": 1,
        "executable_path": "",
        "proxy_url": "",
        "health_url": DEFAULT_HEALTH_URL,
        "require_proxy_for_telegram": True,
    }
    if not path.is_file():
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Не удалось прочитать сетевые настройки: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Сетевые настройки имеют неподдерживаемую схему.")
    executable = raw.get("executable_path", "")
    proxy = raw.get("proxy_url", "")
    health = raw.get("health_url", DEFAULT_HEALTH_URL)
    require = raw.get("require_proxy_for_telegram", True)
    if not isinstance(executable, str) or len(executable) > 2048:
        raise ValueError("Путь v2RayTun должен быть строкой длиной до 2048 символов.")
    if not isinstance(proxy, str) or len(proxy) > 512:
        raise ValueError("Адрес прокси имеет недопустимый формат.")
    if proxy:
        proxy = validate_proxy_url(proxy)
    if not isinstance(health, str):
        raise ValueError("URL проверки сети должен быть строкой.")
    health = validate_health_url(health)
    if not isinstance(require, bool):
        raise ValueError("require_proxy_for_telegram должен быть логическим значением.")
    return {
        "schema_version": 1,
        "executable_path": executable,
        "proxy_url": proxy,
        "health_url": health,
        "require_proxy_for_telegram": require,
    }


def save_network_settings(path: Path, settings: dict[str, Any]) -> None:
    normalized = {
        "schema_version": 1,
        "executable_path": str(settings.get("executable_path") or "").strip(),
        "proxy_url": validate_proxy_url(str(settings.get("proxy_url") or "")) if settings.get("proxy_url") else "",
        "health_url": validate_health_url(str(settings.get("health_url") or DEFAULT_HEALTH_URL)),
        "require_proxy_for_telegram": settings.get("require_proxy_for_telegram", True),
    }
    if not isinstance(normalized["require_proxy_for_telegram"], bool):
        raise ValueError("require_proxy_for_telegram должен быть логическим значением.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    settings.update(normalized)

from __future__ import annotations

import ctypes
import os
import subprocess
import webbrowser
from urllib.parse import urlparse

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


def register_windows_tools(
    registry: ToolRegistry,
    allowed_apps: dict[str, tuple[str, ...]],
    allowed_processes: dict[str, str] | None = None,
) -> None:
    allowed_processes = allowed_processes or {}

    def open_app(arguments: dict[str, object]) -> ToolResult:
        if os.name != "nt":
            return ToolResult(False, "Этот инструмент поддерживается только в Windows.")
        alias = str(arguments["app"]).casefold()
        command = allowed_apps.get(alias)
        if not command:
            options = ", ".join(sorted(allowed_apps)) or "список пуст"
            return ToolResult(False, f"'{alias}' не разрешено. Доступно: {options}.")
        if len(command) == 2 and command[0] == "__shell_link__":
            try:
                os.startfile(command[1])
            except OSError as exc:
                return ToolResult(False, f"Не удалось открыть ярлык Windows: {exc}")
        else:
            subprocess.Popen(list(command), shell=False, close_fds=True)
        return ToolResult(True, f"Запущено приложение: {alias}")

    def open_url(arguments: dict[str, object]) -> ToolResult:
        raw_url = str(arguments["url"]).strip()
        candidate = raw_url if "://" in raw_url else f"https://{raw_url}"
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ToolResult(False, "Разрешены только корректные HTTP/HTTPS-ссылки.")
        if not webbrowser.open(candidate, new=2):
            return ToolResult(False, "Windows не смогла открыть ссылку в браузере.")
        return ToolResult(True, f"Открыта ссылка: {candidate}")

    def lock_pc(_: dict[str, object]) -> ToolResult:
        if os.name != "nt":
            return ToolResult(False, "Блокировка поддерживается только в Windows.")
        if not ctypes.windll.user32.LockWorkStation():
            return ToolResult(False, "Windows не подтвердила блокировку.")
        return ToolResult(True, "Компьютер заблокирован.")

    def set_volume(arguments: dict[str, object]) -> ToolResult:
        if os.name != "nt":
            return ToolResult(False, "Управление громкостью поддерживается только в Windows.")
        percent = int(arguments["percent"])
        try:
            from pycaw.pycaw import AudioUtilities
        except ImportError:
            return ToolResult(
                False,
                'Не найден модуль pycaw. Установите поддержку Windows: pip install -e ".[windows]".',
            )
        try:
            device = AudioUtilities.GetSpeakers()
            device.volume_percent = percent
        except Exception as exc:
            return ToolResult(False, f"Не удалось изменить громкость ({type(exc).__name__}): {exc}")
        return ToolResult(True, f"Системная громкость установлена на {percent}%.")

    MEDIA_KEYS = {
        "play_pause": 0xB3,
        "next_track": 0xB5,
        "previous_track": 0xB4,
        "stop": 0xB2,
    }

    def send_media_key(arguments: dict[str, object]) -> ToolResult:
        if os.name != "nt":
            return ToolResult(False, "Медиа-клавиши поддерживаются только в Windows.")
        key = str(arguments["key"])
        vk = MEDIA_KEYS.get(key)
        if vk is None:
            return ToolResult(False, f"Неизвестная медиа-клавиша: {key}.")
        user32 = ctypes.windll.user32
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)
        return ToolResult(True, f"Нажата медиа-клавиша: {key}.")

    def adjust_volume(arguments: dict[str, object]) -> ToolResult:
        if os.name != "nt":
            return ToolResult(False, "Управление громкостью поддерживается только в Windows.")
        delta = int(arguments["delta"])
        if delta == 0:
            return ToolResult(False, "Шаг изменения громкости равен нулю.")
        try:
            from pycaw.pycaw import AudioUtilities
        except ImportError:
            return ToolResult(
                False,
                'Не найден модуль pycaw. Установите поддержку Windows: pip install -e ".[windows]".',
            )
        try:
            device = AudioUtilities.GetSpeakers()
            current = int(device.volume_percent)
            target = max(0, min(100, current + delta))
            if target == current:
                return ToolResult(True, f"Громкость уже на границе диапазона: {current}%.")
            device.volume_percent = target
        except Exception as exc:
            return ToolResult(False, f"Не удалось изменить громкость ({type(exc).__name__}): {exc}")
        return ToolResult(True, f"Громкость изменена на {target}% (было {current}%).")

    def close_process(arguments: dict[str, object]) -> ToolResult:
        if os.name != "nt":
            return ToolResult(False, "Завершение процессов поддерживается только в Windows.")
        alias = str(arguments["process"]).casefold()
        executable = allowed_processes.get(alias)
        if not executable:
            options = ", ".join(sorted(allowed_processes)) or "список пуст"
            return ToolResult(False, f"Процесс '{alias}' не разрешён. Доступно: {options}.")
        try:
            import psutil
        except ImportError:
            return ToolResult(
                False,
                'Не найден модуль psutil. Установите поддержку Windows: pip install -e ".[windows]".',
            )
        matches = []
        try:
            for process in psutil.process_iter(["pid", "name"]):
                if str(process.info.get("name") or "").casefold() == executable.casefold():
                    if process.pid not in {os.getpid(), os.getppid()}:
                        matches.append(process)
            if not matches:
                return ToolResult(False, f"Процесс {executable} не найден.")
            for process in matches:
                process.terminate()
            _, alive = psutil.wait_procs(matches, timeout=3)
            if alive:
                return ToolResult(
                    False,
                    f"{len(alive)} процесс(ов) {executable} не завершились штатно; принудительно не закрывал.",
                )
        except (psutil.AccessDenied, psutil.NoSuchProcess) as exc:
            return ToolResult(False, f"Windows не разрешила закрыть процесс: {exc}")
        return ToolResult(True, f"Процесс {executable} закрыт.")

    registry.register(ToolSpec(
        name="open_app",
        description="Запустить приложение Windows по alias из allowlist. Передавай только alias.",
        parameters={
            "type": "object",
            "properties": {"app": {"type": "string", "minLength": 1}},
            "required": ["app"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=open_app,
    ))
    registry.register(ToolSpec(
        name="open_url",
        description="Открыть HTTP или HTTPS ссылку в браузере по прямому запросу пользователя.",
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "minLength": 3, "maxLength": 2048}},
            "required": ["url"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=open_url,
    ))
    registry.register(ToolSpec(
        name="lock_pc",
        description="Заблокировать текущую сессию Windows.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk=RiskLevel.CONFIRM,
        handler=lock_pc,
    ))
    registry.register(ToolSpec(
        name="set_volume",
        description="Установить системную громкость Windows в диапазоне 0..100 процентов.",
        parameters={
            "type": "object",
            "properties": {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
            "required": ["percent"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=set_volume,
    ))
    registry.register(ToolSpec(
        name="send_media_key",
        description="Отправить системную медиа-клавишу Windows: play_pause, next_track, previous_track или stop.",
        parameters={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "enum": ["play_pause", "next_track", "previous_track", "stop"],
                }
            },
            "required": ["key"],
            "additionalProperties": False,
        },
        risk=RiskLevel.SAFE,
        handler=send_media_key,
    ))
    registry.register(ToolSpec(
        name="adjust_volume",
        description="Изменить системную громкость на дельту (целое число, может быть отрицательным).",
        parameters={
            "type": "object",
            "properties": {"delta": {"type": "integer", "minimum": -100, "maximum": 100}},
            "required": ["delta"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=adjust_volume,
    ))
    registry.register(ToolSpec(
        name="close_process",
        description="Штатно завершить процесс только по alias из локального allowlist.",
        parameters={
            "type": "object",
            "properties": {"process": {"type": "string", "minLength": 1}},
            "required": ["process"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=close_process,
    ))

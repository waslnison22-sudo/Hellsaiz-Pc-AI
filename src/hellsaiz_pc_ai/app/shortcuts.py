from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path


_LOGGER = logging.getLogger(__name__)


def ensure_desktop_shortcut(
    launcher_path: Path, *, is_windows: bool | None = None
) -> bool:
    """Create or repair the current user's desktop shortcut to the stable launcher.

    This runs from the versioned application bundle, but always points at the
    root-level launcher so future app versions can be swapped without changing
    the shortcut. PowerShell receives paths through environment variables;
    paths are never interpolated into executable PowerShell code.
    """
    if is_windows is None:
        is_windows = os.name == "nt"
    if not is_windows:
        return False

    launcher = launcher_path.expanduser().resolve()
    if not launcher.is_file():
        _LOGGER.warning("Desktop shortcut skipped: launcher not found at %s", launcher)
        return False

    script = r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($desktop)) {
    throw 'Windows did not return the Desktop directory.'
}
$shortcutPath = Join-Path $desktop 'Hellsaiz PC AI.lnk'
$targetPath = $env:HELLSAIZ_LAUNCHER_PATH
$shortcut = $shell.CreateShortcut($shortcutPath)
if ((Test-Path -LiteralPath $shortcutPath) -and
    $shortcut.TargetPath -ieq $targetPath -and
    $shortcut.WorkingDirectory -ieq (Split-Path -Parent $targetPath)) {
    exit 0
}
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = Split-Path -Parent $targetPath
$shortcut.IconLocation = "$targetPath,0"
$shortcut.Description = 'Запуск Hellsaiz PC AI'
$shortcut.Save()
"""
    environment = os.environ.copy()
    environment["HELLSAIZ_LAUNCHER_PATH"] = str(launcher)

    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _LOGGER.warning("Could not create the desktop shortcut: %s", exc)
        return False
    return True

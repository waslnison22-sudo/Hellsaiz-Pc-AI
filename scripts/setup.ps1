$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if ($env:OS -ne "Windows_NT") {
    throw "Hellsaiz PC AI source setup is supported only on Windows 10/11 x64."
}

function Test-PythonRuntime {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @()
    )
    $probe = "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)"
    try {
        $null = & $Executable @Arguments -c $probe 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Find-PythonRuntime {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @("3.12", "3.11")) {
            $arguments = @("-$version")
            if (Test-PythonRuntime -Executable $launcher.Source -Arguments $arguments) {
                return [pscustomobject]@{ Executable = $launcher.Source; Arguments = $arguments }
            }
        }
    }

    $candidates = @()
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) { $candidates += $pythonCommand.Source }
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
        $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe")
    }
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles "Python312\python.exe")
        $candidates += (Join-Path $env:ProgramFiles "Python311\python.exe")
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ((Test-Path $candidate -PathType Leaf) -and (Test-PythonRuntime -Executable $candidate)) {
            return [pscustomobject]@{ Executable = $candidate; Arguments = @() }
        }
    }
    return $null
}

$runtime = Find-PythonRuntime
if (-not $runtime) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python 3.11 or 3.12 is required. Install Python 3.12, then run INSTALL.bat again. Download: https://www.python.org/downloads/windows/"
    }

    Write-Host "Python 3.12 was not found. Installing it for the current Windows user through winget..."
    & $winget.Source install --id Python.Python.3.12 --exact --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        throw "Python installation through winget failed (exit code $LASTEXITCODE). Install Python 3.12 manually, then run INSTALL.bat again."
    }

    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
    $runtime = Find-PythonRuntime
    if (-not $runtime) {
        throw "Python installation completed, but Python 3.12 could not be located. Restart Windows or install Python 3.12 manually, then run INSTALL.bat again."
    }
}

Write-Host "Using Python: $($runtime.Executable) $($runtime.Arguments -join ' ')"
$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$validExistingVenv = $false
if (Test-Path $venvPython -PathType Leaf) {
    $validExistingVenv = Test-PythonRuntime -Executable $venvPython
}
if (-not $validExistingVenv) {
    if (Test-Path $venvPath) {
        Remove-Item -Recurse -Force $venvPath
    }
    $createVenvArguments = @($runtime.Arguments) + @("-m", "venv", $venvPath)
    & $runtime.Executable @createVenvArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the Python virtual environment (exit code $LASTEXITCODE)."
    }
}
if (-not (Test-Path $venvPython -PathType Leaf)) {
    throw "The Python virtual environment was not created: $venvPython"
}

Write-Host "Installing Hellsaiz PC AI and Windows, voice, and vision dependencies..."
& $venvPython -m pip install --disable-pip-version-check --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed (exit code $LASTEXITCODE)."
}
& $venvPython -m pip install --disable-pip-version-check -e ".[windows,voice,vision]"
if ($LASTEXITCODE -ne 0) {
    throw "Application dependency installation failed (exit code $LASTEXITCODE)."
}
& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) {
    throw "Installed Python packages have dependency conflicts. Review the pip output above."
}

$diagnostic = @'
import importlib
modules = (
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "hellsaiz_pc_ai.app.desktop",
    "hellsaiz_pc_ai.tools.ui_automation",
    "hellsaiz_pc_ai.tools.screen_ocr",
    "hellsaiz_pc_ai.tools.ocr_models",
    "rapidocr",
    "onnxruntime",
    "mss",
    "pywinauto",
    "comtypes",
    "vosk",
    "piper",
    "sounddevice",
    "numpy",
    "psutil",
    "pycaw.pycaw",
    "pynput",
)
for name in modules:
    importlib.import_module(name)
    print("OK", name)
'@
& $venvPython -c $diagnostic
if ($LASTEXITCODE -ne 0) {
    throw "A required application module could not be imported. The source installation is incomplete."
}

$configDir = Join-Path $env:LOCALAPPDATA "HellsaizPC_AI"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$config = Join-Path $configDir "config.toml"
if (-not (Test-Path $config -PathType Leaf)) {
    Copy-Item (Join-Path $projectRoot "config\default.toml") $config
}

Write-Host ""
Write-Host "Hellsaiz PC AI 0.1.4 source setup completed."
Write-Host "Your user data remains in: $configDir"
Write-Host "Start the application with RUN.bat."
Write-Host "This source mode does not include the signed in-app updater; keep your existing 0.1.3 installation until the official 0.1.4 release is published."

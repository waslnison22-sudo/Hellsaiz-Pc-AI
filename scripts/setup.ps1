$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' is missing. Install Python 3.11+ from python.org."
}
# Select the configured default Python 3 runtime, then enforce the minimum version.
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    py -0p
    throw "Python 3.11 or newer is required. Install it, then run this script again."
}
py -3 -m venv .venv
$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Virtual environment creation failed." }
& $python -m pip install --upgrade pip
& $python -m pip install -e ".[dev]"
$configDir = Join-Path $env:LOCALAPPDATA "HellsaizPC_AI"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$config = Join-Path $configDir "config.toml"
if (-not (Test-Path $config)) {
    Copy-Item (Join-Path (Get-Location) "config\default.toml") $config
}
Write-Host "Setup complete. Run .\scripts\run.ps1"

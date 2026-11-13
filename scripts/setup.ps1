$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' is missing. Install Python 3.11+."
}
py -3.11 -m venv .venv
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

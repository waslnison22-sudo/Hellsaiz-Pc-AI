$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python -PathType Leaf)) {
    throw "The source environment is not installed. Run INSTALL.bat first."
}
& $python -m hellsaiz_pc_ai
if ($LASTEXITCODE -ne 0) {
    throw "Hellsaiz PC AI exited with code $LASTEXITCODE."
}

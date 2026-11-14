$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

python -m pip install -e ".[build,windows,voice]"
if ($LASTEXITCODE -ne 0) { throw "Windows build dependencies could not be installed." }

Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue

pyinstaller --noconfirm --clean --onedir --windowed --uac-admin --name HellsaizPC_AI --distpath dist/app --workpath build/app --collect-all vosk --collect-all sounddevice --collect-all pycaw --collect-all pynput --collect-all piper --collect-all onnxruntime src/hellsaiz_pc_ai/__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build the desktop application." }

pyinstaller --noconfirm --clean --onefile --windowed --uac-admin --name HellsaizLauncher --distpath dist/tools --workpath build/launcher src/hellsaiz_pc_ai/launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build the launcher." }

pyinstaller --noconfirm --clean --onefile --windowed --uac-admin --name HellsaizUpdater --distpath dist/tools --workpath build/updater --collect-all cryptography src/hellsaiz_pc_ai/updater.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build the updater." }

$required = @(
    "dist/app/HellsaizPC_AI/HellsaizPC_AI.exe",
    "dist/tools/HellsaizLauncher.exe",
    "dist/tools/HellsaizUpdater.exe"
)
foreach ($path in $required) {
    if (-not (Test-Path $path -PathType Leaf)) {
        throw "Required Windows executable was not created: $path"
    }
    if ((Get-Item $path).Length -le 0) {
        throw "Windows executable is empty: $path"
    }
}

$metadataDir = "dist/preview"
New-Item -ItemType Directory -Force -Path $metadataDir | Out-Null
$version = python -c 'from hellsaiz_pc_ai.version import APP_VERSION; print(APP_VERSION)'
if ($LASTEXITCODE -ne 0) { throw "Could not read the embedded application version." }
$metadata = @(
    "Build type: non-release preview",
    "Version: $version",
    "Commit: $env:GITHUB_SHA",
    "Runtime: Windows x64",
    "Application: onedir PyInstaller bundle",
    "Launcher: onefile executable",
    "Updater: onefile executable",
    "Signing: not performed; this preview is not a release package"
)
$metadata | Set-Content -Path (Join-Path $metadataDir "BUILD-METADATA.txt") -Encoding utf8

Compress-Archive -Path @(
    "dist/app/HellsaizPC_AI",
    "dist/tools/HellsaizLauncher.exe",
    "dist/tools/HellsaizUpdater.exe",
    "dist/preview/BUILD-METADATA.txt"
) -DestinationPath "dist/preview/HellsaizPC_AI-windows-x64-preview.zip" -CompressionLevel Optimal -Force

if (-not (Test-Path "dist/preview/HellsaizPC_AI-windows-x64-preview.zip" -PathType Leaf)) {
    throw "Preview ZIP was not created."
}
if ((Get-Item "dist/preview/HellsaizPC_AI-windows-x64-preview.zip").Length -le 0) {
    throw "Preview ZIP is empty."
}

Write-Host "Windows preview build completed. This is an unsigned test artifact, not a public release."

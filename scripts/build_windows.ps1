param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python scripts/apply_pending_patches.py
if ($LASTEXITCODE -ne 0) { throw "Pending patches failed to apply; check docs/patches/." }

$Version = $Version.TrimStart("v")
python scripts/set_version.py $Version
if ($LASTEXITCODE -ne 0) { throw "Could not set the application version." }

python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
python -m pip install -e ".[build,windows,voice,vision]"
if ($LASTEXITCODE -ne 0) { throw "Application dependencies could not be installed." }

Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue

pyinstaller --noconfirm --clean --onedir --windowed --uac-admin --name HellsaizPC_AI --icon src/hellsaiz_pc_ai/assets/hellsaiz_icon.ico --distpath dist/app --workpath build/app --collect-all vosk --collect-all sounddevice --collect-all pyttsx3 --hidden-import pyttsx3.drivers.sapi5 --collect-all pycaw --collect-all pynput --collect-all pywinauto --collect-all comtypes --collect-all piper --collect-all onnxruntime --collect-all rapidocr --collect-all mss --collect-all cv2 --hidden-import PySide6.QtSvg --collect-submodules hellsaiz_pc_ai.companion src/hellsaiz_pc_ai/__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build the desktop application." }

pyinstaller --noconfirm --clean --onefile --windowed --uac-admin --name HellsaizLauncher --icon src/hellsaiz_pc_ai/assets/hellsaiz_icon.ico --distpath dist/tools --workpath build/launcher src/hellsaiz_pc_ai/launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build the launcher." }

pyinstaller --noconfirm --clean --onefile --windowed --uac-admin --name HellsaizUpdater --icon src/hellsaiz_pc_ai/assets/hellsaiz_icon.ico --distpath dist/tools --workpath build/updater --collect-all cryptography src/hellsaiz_pc_ai/updater.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build the update helper." }

python scripts/package_release.py --version $Version --app-dir dist/app/HellsaizPC_AI --launcher dist/tools/HellsaizLauncher.exe --updater dist/tools/HellsaizUpdater.exe
if ($LASTEXITCODE -ne 0) { throw "Release package generation failed." }

$fullPackage = "dist/release-assets/HellsaizPC_AI-windows-x64-full.zip"
$portablePackage = "dist/release-assets/HellsaizPC_AI-windows-x64-portable.zip"
foreach ($package in @($fullPackage, $portablePackage)) {
    if (-not (Test-Path $package -PathType Leaf)) { throw "Required ZIP package was not created: $package" }
    if ((Get-Item $package).Length -le 0) { throw "ZIP package is empty: $package" }
}

Write-Host "Portable ZIP and signed updater packages are ready in dist/release-assets/."

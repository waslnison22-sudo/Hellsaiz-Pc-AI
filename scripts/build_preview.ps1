$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

python -m pip install -e ".[build,windows,voice]"
if ($LASTEXITCODE -ne 0) { throw "Windows build dependencies could not be installed." }

Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue

pyinstaller --noconfirm --clean --onedir --windowed --uac-admin --name HellsaizPC_AI --distpath dist/app --workpath build/app --collect-all vosk --collect-all sounddevice --collect-all pycaw --collect-all pynput --collect-all pywinauto --collect-all comtypes --collect-all piper --collect-all onnxruntime src/hellsaiz_pc_ai/__main__.py
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

$version = python -c 'from hellsaiz_pc_ai.version import APP_VERSION; print(APP_VERSION)'
if ($LASTEXITCODE -ne 0) { throw "Could not read the embedded application version." }

$installRoot = "dist/install"
$versionRoot = Join-Path $installRoot "versions/$version"
New-Item -ItemType Directory -Force -Path $versionRoot | Out-Null
Copy-Item "dist/app/HellsaizPC_AI/*" $versionRoot -Recurse -Force
Copy-Item "dist/tools/HellsaizLauncher.exe" $installRoot -Force
Copy-Item "dist/tools/HellsaizUpdater.exe" $installRoot -Force
$activeJson = @{
    schema_version = 1
    active_version = $version
    previous_version = $null
} | ConvertTo-Json
[System.IO.File]::WriteAllText(
    (Join-Path $installRoot "active.json"),
    $activeJson,
    [System.Text.UTF8Encoding]::new($false)
)

$innoCompiler = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6/ISCC.exe"
if (-not (Test-Path $innoCompiler)) {
    choco install innosetup --yes --no-progress
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup installation failed." }
}
if (-not (Test-Path $innoCompiler)) {
    throw "Inno Setup compiler ISCC.exe was not found."
}
& $innoCompiler "/DAppVersion=$version" "installer/HellsaizPC_AI.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup installer compilation failed." }
if (-not (Test-Path "dist/HellsaizPC_AI_Setup.exe" -PathType Leaf)) {
    throw "The Windows installer executable was not created."
}

function Invoke-ExecutableSmokeTest {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $process = Start-Process -FilePath (Resolve-Path $Executable) -ArgumentList "--self-test" -WorkingDirectory (Resolve-Path $WorkingDirectory) -PassThru
    if (-not $process.WaitForExit(300000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        $diagnosticLog = Join-Path $env:TEMP "HellsaizPC_AI-package-self-test.log"
        if ($Label -like "*Desktop application*" -and (Test-Path $diagnosticLog)) {
            $tail = (Get-Content $diagnosticLog -Tail 30) -join [Environment]::NewLine
            throw "$Label self-test timed out. Last diagnostic lines:`n$tail"
        }
        throw "$Label self-test timed out."
    }
    if ($process.ExitCode -ne 0) {
        $diagnosticLog = Join-Path $env:TEMP "HellsaizPC_AI-package-self-test.log"
        if ($Label -like "*Desktop application*" -and (Test-Path $diagnosticLog)) {
            $details = Get-Content $diagnosticLog -Raw
            Write-Host "Packaged application self-test diagnostics:`n$details"
        }
        throw "$Label self-test failed with exit code $($process.ExitCode)."
    }
    Write-Host "$Label self-test passed."
}

Invoke-ExecutableSmokeTest -Executable "dist/app/HellsaizPC_AI/HellsaizPC_AI.exe" -WorkingDirectory "dist/app/HellsaizPC_AI" -Label "Desktop application"
Invoke-ExecutableSmokeTest -Executable "dist/install/HellsaizLauncher.exe" -WorkingDirectory "dist/install" -Label "Application launcher"
Invoke-ExecutableSmokeTest -Executable "dist/tools/HellsaizUpdater.exe" -WorkingDirectory "dist/tools" -Label "Update helper"

$smokeInstallRoot = Join-Path $env:RUNNER_TEMP "HellsaizPC_AI-Installer-Smoke"
Remove-Item -Recurse -Force $smokeInstallRoot -ErrorAction SilentlyContinue
$setupProcess = Start-Process -FilePath (Resolve-Path "dist/HellsaizPC_AI_Setup.exe") -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/DIR=$smokeInstallRoot"
) -PassThru -Wait
if ($setupProcess.ExitCode -ne 0) {
    throw "Inno Setup installation smoke test failed with exit code $($setupProcess.ExitCode)."
}
$installedActive = Get-Content (Join-Path $smokeInstallRoot "active.json") -Raw | ConvertFrom-Json
if (-not $installedActive.active_version) {
    throw "Installed active.json does not select an application version."
}
$installedVersionRoot = Join-Path $smokeInstallRoot "versions/$($installedActive.active_version)"
Invoke-ExecutableSmokeTest -Executable (Join-Path $installedVersionRoot "HellsaizPC_AI.exe") -WorkingDirectory $installedVersionRoot -Label "Installed desktop application"
Invoke-ExecutableSmokeTest -Executable (Join-Path $smokeInstallRoot "HellsaizLauncher.exe") -WorkingDirectory $smokeInstallRoot -Label "Installed launcher"
Invoke-ExecutableSmokeTest -Executable (Join-Path $smokeInstallRoot "HellsaizUpdater.exe") -WorkingDirectory $smokeInstallRoot -Label "Installed updater"

$uninstaller = Join-Path $smokeInstallRoot "unins000.exe"
if (-not (Test-Path $uninstaller -PathType Leaf)) {
    throw "The Windows installer did not register an uninstaller."
}
$uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART"
) -PassThru -Wait
if ($uninstallProcess.ExitCode -ne 0) {
    throw "Installer uninstall smoke test failed with exit code $($uninstallProcess.ExitCode)."
}

$metadataDir = "dist/preview"
New-Item -ItemType Directory -Force -Path $metadataDir | Out-Null
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
    "dist/HellsaizPC_AI_Setup.exe",
    "dist/preview/BUILD-METADATA.txt"
) -DestinationPath "dist/preview/HellsaizPC_AI-windows-x64-preview.zip" -CompressionLevel Optimal -Force

if (-not (Test-Path "dist/preview/HellsaizPC_AI-windows-x64-preview.zip" -PathType Leaf)) {
    throw "Preview ZIP was not created."
}
if ((Get-Item "dist/preview/HellsaizPC_AI-windows-x64-preview.zip").Length -le 0) {
    throw "Preview ZIP is empty."
}

Write-Host "Windows preview build completed. This is an unsigned test artifact, not a public release."

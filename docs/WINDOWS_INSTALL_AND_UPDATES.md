# Windows installer and updates

## Build

The supported Windows distribution is a PyInstaller **onedir** application installed under Program Files by Inno Setup. A stable launcher starts the active version from `versions/<version>`. The updater is a separate elevated process; it waits for the desktop process to exit, stages a new version, validates every file against a signed manifest, switches `active.json`, launches the new version, and rolls back if the startup health marker is not written.

For a local build on Windows 10/11 x64:

```powershell
$env:HELLSAIZ_UPDATE_SIGNING_KEY = "<base64 Ed25519 private key>"
.scripts\build_windows.ps1 -Version 0.1.1
```

The installer is written to `dist/HellsaizPC_AI_Setup.exe`.

## Release signing

GitHub Actions needs one repository Actions secret:

- Name: `HELLSAIZ_UPDATE_SIGNING_KEY`
- Value: base64-encoded raw Ed25519 private key bytes.

Add it in **Repository → Settings → Secrets and variables → Actions → New repository secret**. Never commit the private key or place it in the application. The matching public key is pinned in `src/hellsaiz_pc_ai/update_trust.py`.

Push a stable semantic-version tag such as `v0.1.1` to run `.github/workflows/release-windows.yml`. The workflow builds the installer, full ZIP, signed manifest and signature. If a trusted previous release exists, it also emits a delta ZIP containing changed files. The updater still validates the final installed file set and hashes; if a delta is missing, it downloads the full package.

## Important limitations

- The GitHub repository is private. The app's update settings require a fine-grained GitHub token with read-only **Contents** access to this repository. The token is stored using Windows DPAPI for the current Windows user.
- A private GitHub token is not an application signing key. Keep these credentials separate.
- The GitHub Actions signing secret is needed before the first release can be built.
- The updater retains the active and immediately previous version. User data is stored separately under LocalAppData and is not replaced by updates.
- This pipeline produces an x64 Windows installer. It is not a code-signed publisher certificate installer; Windows SmartScreen may still show an unknown-publisher warning.

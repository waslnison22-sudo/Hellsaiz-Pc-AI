# Windows ZIP distribution and update channel

The Windows release publishes two different ZIP formats. They are intentionally not interchangeable.

## First download: portable archive

`HellsaizPC_AI-windows-x64-portable.zip` is the user-facing download. Extract the complete archive and start `HellsaizLauncher.exe` from its root. It contains `active.json`, the stable launcher and updater, and the complete PyInstaller onedir build under `versions/<version>/`. The launcher selects the version declared by `active.json`.

On the first successful application start, the versioned app creates or repairs a desktop shortcut named `Hellsaiz PC AI.lnk`. The shortcut always targets the root-level `HellsaizLauncher.exe`, not the versioned application executable, so it remains valid when the updater activates a newer version. The Inno Setup installer also enables the desktop shortcut task by default.

## Updating an existing 0.1.3 installation

Do not uninstall the old application and do not extract the update ZIP over the installation folder. Keep the existing installation directory, including the root-level launcher and updater. Start Hellsaiz PC AI 0.1.3, open **Настройки → Обновления**, save a fine-grained GitHub token with read-only **Contents** permission for this private repository, check for updates, and choose the manual install action when 0.1.5 is offered.

The updater stages 0.1.5 in a separate `versions/0.1.5/` directory, verifies the signed manifest and every file hash, then switches `active.json`. It keeps 0.1.3 until the new application reports a successful startup. Chat history, profiles, wallpapers, downloaded voice models, reminders, and other user data remain outside the version directory and are not overwritten. If startup validation fails, the active version is restored to 0.1.3 automatically.

The update process requires the root-level `HellsaizLauncher.exe` and `HellsaizUpdater.exe` from the existing portable installation. If either file is missing, use the full installer or portable package to repair the installation before applying an in-app update.

## Internal update payload

`HellsaizPC_AI-windows-x64-full.zip` is for the updater only. Its files are at ZIP root and match the signed manifest records exactly. Delta archives, when available, likewise contain only changed manifest-listed files at ZIP root. Do not extract these archives as a first-time installation; doing so omits the launcher layout and active-version metadata.

The updater verifies the pinned Ed25519 manifest signature, file paths, sizes and SHA-256 digests before activating the staged version. The active build remains intact until validation succeeds. A failed health start restores the previous version; one previous version is retained. User data is stored separately under LocalAppData and is not removed by updates. Download and installation are manual user actions; automatic checks only report availability.

## Release acceptance test

Before uploading a new release, the Windows workflow downloads the previous stable portable package and runs its own launcher/updater against the newly signed full ZIP. For the current 0.1.5 baseline this is an actual 0.1.3 → 0.1.5 update, not a mocked updater call. The workflow verifies:

- the previous 0.1.3 launcher and updater can stage and activate the new version;
- the new application writes `health/0.1.5.ok` after creating its main window;
- `active.json` selects 0.1.5 and the 0.1.3 folder remains available for rollback;
- a separate LocalAppData sentinel remains byte-for-byte unchanged.

Release publication is blocked if any of those checks fail. The previous 0.1.3 portable package is therefore a required release input, not merely a convenience download.

## Private update channel

For a private repository, enter a fine-grained GitHub Personal Access Token with read-only **Contents** permission for the repository. The token is protected with Windows DPAPI for the current Windows account and is not written to ordinary `config.toml` or chat history. Keep it separate from the release signing key.

The release workflow runs on a Windows runner, builds the onedir app, launcher and updater, creates both ZIP formats, compiles the Inno Setup installer, and publishes the signed manifest, signature, update ZIP, portable ZIP, and Setup.exe. Before packaging, it verifies that the configured private signing key matches the public key embedded in the updater; a mismatch fails the release build.

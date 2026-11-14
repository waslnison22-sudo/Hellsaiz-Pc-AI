# Windows ZIP distribution and update channel

The Windows release publishes two different ZIP formats. They are intentionally not interchangeable.

## First download: portable archive

`HellsaizPC_AI-windows-x64-portable.zip` is the user-facing download. Extract the complete archive and start `HellsaizLauncher.exe` from its root. It contains `active.json`, the stable launcher and updater, and the complete PyInstaller onedir build under `versions/<version>/`. The launcher selects the version declared by `active.json`.

## Internal update payload

`HellsaizPC_AI-windows-x64-full.zip` is for the updater only. Its files are at ZIP root and match the signed manifest records exactly. Delta archives, when available, likewise contain only changed manifest-listed files at ZIP root. Do not extract these archives as a first-time installation; doing so omits the launcher layout and active-version metadata.

The updater verifies the pinned Ed25519 manifest signature, file paths, sizes and SHA-256 digests before activating the staged version. The active build remains intact until validation succeeds. A failed health start restores the previous version; one previous version is retained. User data is stored separately under LocalAppData and is not removed by updates. Download and installation are manual user actions; automatic checks only report availability.

## Private update channel

For a private repository, enter a fine-grained GitHub Personal Access Token with read-only **Contents** permission for the repository. The token is protected with Windows DPAPI for the current Windows account and is not written to ordinary `config.toml` or chat history. Keep it separate from the release signing key.

The release workflow runs on a Windows runner, builds the onedir app, launcher and updater, creates both ZIP formats, and publishes the signed manifest and signature. It does not publish Setup.exe.

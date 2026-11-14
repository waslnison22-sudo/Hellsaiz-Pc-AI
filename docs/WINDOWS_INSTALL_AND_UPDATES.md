# Windows portable distribution and updates

## First installation

The supported user distribution is a ZIP archive. It does not contain a Setup.exe installer.

Download **HellsaizPC_AI-windows-x64-portable.zip**, extract the archive into a writable folder, and launch **HellsaizLauncher.exe** from the extracted root.

The portable archive has this structure:

```text
HellsaizPC_AI/
├── active.json
├── HellsaizLauncher.exe
├── HellsaizUpdater.exe
└── versions/
    └── <version>/
        ├── HellsaizPC_AI.exe
        └── PyInstaller runtime files...
```

Do not launch `HellsaizPC_AI.exe` from inside `versions/<version>` directly. The Launcher reads `active.json`, selects the active version and starts the application. The application detects the installation root from its location and enables its update flow.

Keep the whole extracted folder together. Do not move or delete `active.json`, Launcher, Updater or the `versions` directory individually.

## Two ZIP files have different purposes

Each release publishes two ZIP packages:

- `HellsaizPC_AI-windows-x64-portable.zip` — for the first download and manual extraction. Contains `active.json`, Launcher, Updater and the versioned desktop application.
- `HellsaizPC_AI-windows-x64-full.zip` — internal updater payload only. It contains files listed in the signed version manifest and is downloaded by the application during an update. It is not a first-install archive and must not be extracted by the user over the portable folder.

A delta ZIP may also be published. It is an internal update payload and is never a first-install package.

## Connecting the private update channel

The GitHub repository is private, so the application needs a read-only token to check and download releases.

1. Open GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens.
2. Create a token limited to the `waslnison22-sudo/Hellsaiz-Pc-AI` repository.
3. Grant **Repository permissions → Contents → Read-only**.
4. In Hellsaiz PC AI → Settings → Updates, paste the token into the GitHub Token field and press **Save key**.

The token is encrypted with Windows DPAPI for the current Windows user. It is not written to `config.toml`, the signed release manifest or application logs. A GitHub token is not the Ed25519 release-signing key.

The automatic check runs when the application starts if the corresponding checkbox is enabled. Automatic checking only detects and reports a new version; it does not install updates silently.

To install an available version, choose **Download and install**. The app downloads the internal updater ZIP, verifies the signed manifest and payload hashes, starts the separate updater helper, and closes. The helper stages the new version, waits for the desktop process to exit, switches the active version and starts Launcher again. If the health marker is not written, the helper restores the previous active version.

## Release build

The Windows release workflow builds:
- the versioned PyInstaller onedir application;
- the stable Launcher and Updater executables;
- the signed manifest and signature;
- the internal full ZIP payload;
- the portable ZIP for first installation.

The release signing key is stored only as the GitHub Actions secret `HELLSAIZ_UPDATE_SIGNING_KEY`. Never commit it or paste it into the application.

The release workflow is triggered by a version tag such as `v0.1.3`. It does not create Setup.exe.

## Important limitations

- The application must be launched through `HellsaizLauncher.exe` from the extracted portable root for automatic updates to be available.
- The extracted installation directory must be writable by the current Windows user or the elevated app/updater must be allowed to write there.
- The updater retains the active and immediately previous versions for rollback.
- User data is stored separately under LocalAppData and is not replaced by updates.
- Windows may show an unknown-publisher warning because the binaries do not use a commercial Authenticode publisher certificate.

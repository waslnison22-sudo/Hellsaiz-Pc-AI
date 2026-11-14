# HUD and update design

## Main chat and visual style

The default screen is a single chat surface. The product palette is strictly monochrome: near-black canvas, graphite surfaces, neutral grey secondary text, and white primary actions. Avoid decorative panels and high-contrast accent colors. Keep the transcript readable, the composer at the bottom, and AI/voice configuration compact and optional.

## Application discovery and catalog

The app catalog uses known Windows installation sources (Start-menu shortcuts and registry entries) plus explicit file selection for portable or non-registered applications, including EXE and LNK files. A full recursive scan of every drive is intentionally not performed. Catalog entries should emphasize the friendly name, with the full executable path available as secondary text or a tooltip.

## Update channel and ZIP contracts

The user-facing portable download is `HellsaizPC_AI-windows-x64-portable.zip`. Its root has `active.json`, `HellsaizLauncher.exe`, `HellsaizUpdater.exe`, and `versions/<version>/` containing the complete onedir application. Users extract the archive and launch the root launcher.

The internal full and delta update ZIPs are a separate format: they contain only files at ZIP root that correspond to the signed manifest, and are extracted to a staging directory. Never wrap these payloads in the portable folder structure: that would break manifest file verification.

The update settings support checking the configured GitHub release channel. An optional access token is protected with Windows DPAPI and is never written to ordinary TOML settings or chat history. Checking for updates does not install them. Download and installation require an explicit user action. The updater verifies the signed manifest, file paths, sizes and hashes before activation; it retains the current build until the new version passes its health start and keeps one previous version for rollback.

The base package contains the desktop runtime only. LLM weights, speech models, voices, and optional plug-ins are installed separately and stored in user-selected locations.


## 0.1.4 — personal glass HUD

- Navigation is a permanent graphite glass sidebar; the Windows title bar remains native.
- The workspace uses a pure black background by default. Optional static images and GIFs are copied to the per-user local data directory; no external URL wallpaper loading is supported.
- The "Обои" page selects local wallpapers and restores black on reset.
- The "Голоса" page manages Piper ONNX models, downloads each model with its JSON config and MODEL_CARD, and can select Piper or Windows SAPI5 for speech output.
- The 3D companion is deliberately postponed until the command and voice foundation is stable.

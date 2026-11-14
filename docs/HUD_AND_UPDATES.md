# HUD and update design

## Main chat

The default screen is a single chat surface. It has no companion, system dashboard, activity feed, quick-action grid, or always-visible "system active" banner.

The composer contains the message field, microphone input, a compact **AI / Voice** control, and send. The AI / Voice control opens a short animated panel above the composer. It owns the local AI endpoint/model profile, speech output voice, voice test, and automatic reply speech setting. Secondary areas are kept in separate tabs: reminders, scenarios, application catalog, and settings.

The visual system is monochrome: near-black canvas, graphite surfaces, neutral borders, restrained white primary action, no red accent. The chat transcript is the main visual focus; spacing and typography take precedence over glass effects.

## Application discovery and catalog

The app catalog has two discovery paths:

1. Known Windows installation sources: Start-menu shortcuts and registry entries (Uninstall metadata and App Paths).
2. Explicit file selection for portable or non-registered applications, including EXE and LNK files from any mounted drive.

A full recursive scan of every drive is intentionally not performed. It is slow, noisy, can traverse private folders, and is not a reliable way to identify installed software. Users may add, review, and retain exact executable/shortcut paths. Paths are checked at selection time and are revalidated by Windows when launched. The application remains in a typed allowlist; natural-language aliases resolve only to a registered catalog entry.

## Update channel

The Settings page supports a release check against the configured GitHub repository. An optional access token is protected with Windows DPAPI and is never written to the ordinary TOML profile or logs. Without a token the public latest-release endpoint is used. A release candidate is considered a Windows package only when a Windows ZIP asset with a SHA-256 digest is attached.

The remaining productization stage is a versioned Windows onedir build plus the updater bootstrapper. The intended safe flow is:

1. Check a signed release manifest and compare its version with the installed build.
2. Download changed files only into a staging directory.
3. Verify the manifest signature, every file hash, size and safe relative path before extracting anything.
4. Keep the current version intact while the staged version is verified.
5. Apply the update through a separate helper after the desktop process exits; retain one rollback version.
6. Remove old versions and temporary files only after the new version completes a successful health start.

The base package contains the desktop runtime only. LLM weights, Vosk/Whisper models, Piper voices, and optional plug-ins are installed separately and stored in user-selected locations. Updates must never download or replace those large assets unless the user explicitly requests a model/voice update.

The current implementation includes the Settings release check and protected access-key storage. Automatic package installation, signed-manifest verification, differential file download, and rollback are not claimed complete until the Windows packaging/release pipeline and updater bootstrapper are shipped and tested.

# 0.1.5 release readiness

This is the single release gate for the first usable Hellsaiz PC AI 0.1.5 build. There is no 0.1.4 release target.

## Release scope

0.1.5 is a local-first Windows desktop assistant for personal use, not a finished commercial product.

- Rule-based local commands and workflows must work without an LLM.
- Offline STT/TTS uses local engines; downloadable speech models remain in the user's data directory.
- Screen OCR is optional and disabled by default.
- Telegram and v2RayTun are optional integrations, disabled until configured.
- The companion in this release is renderer-neutral only; no avatar renderer or proprietary model assets are shipped.

## Required publication gates

- [x] Linux core pytest matrix passes on Python 3.11 and 3.12.
- [x] Windows full pytest matrix passes on Python 3.11 and 3.12.
- [x] Windows preview executable package builds.
- [x] Frozen desktop, launcher and updater self-tests pass.
- [x] Inno Setup installer compiles.
- [x] Silent install, installed executable self-tests and silent uninstall pass.
- [x] Release package is signed with the repository Actions secret `HELLSAIZ_UPDATE_SIGNING_KEY`.
- [x] Signed manifest verifies against the updater's embedded public key.
- [x] Full, delta and portable ZIPs validate against the generated manifest.
- [x] Actual 0.1.3 portable installation updates to 0.1.5 using the existing updater.
- [x] Update writes the 0.1.5 health marker, retains the 0.1.3 rollback copy and preserves LocalAppData byte-for-byte.
- [x] Failure-path integration test restores 0.1.3 and removes the failed staged version.
- [x] GitHub Release `v0.1.5` contains all required downloadable assets.

## CI evidence

The development CI run for commit `7a6ec31734937ed66795f1848c36447bc5c0f917` completed successfully:

- Workflow run: https://github.com/waslnison22-sudo/Hellsaiz-Pc-AI/actions/runs/43824145121
- Linux Python 3.11 and 3.12 test matrices: passed.
- Windows Python 3.11 and 3.12 test matrices: passed.
- Windows preview executable package: passed.
- Desktop, launcher and updater frozen self-tests: passed.
- Inno Setup compilation and silent install/uninstall smoke tests: passed.

Release acceptance completed successfully on 2026-11-16. The Windows release workflow built the app and installer, validated the signed manifest against the embedded public key, installed and uninstalled the setup silently, and completed the real 0.1.3 → 0.1.5 update test including health marker, user-data preservation and rollback checks.

## Previous stable baseline

The release workflow locates the most recent stable release that actually contains all three baseline files:

- `HellsaizPC_AI-update-manifest.json`
- `HellsaizPC_AI-update-manifest.sig`
- `HellsaizPC_AI-windows-x64-portable.zip`

The empty `v0.1.5` release is excluded as the current tag during its own build. The valid previous baseline is expected to be `v0.1.3`. Never delete or overwrite the `v0.1.3` assets or installed user data.

## Signing secret

The workflow requires the GitHub Actions secret `HELLSAIZ_UPDATE_SIGNING_KEY`. The current GitHub integration cannot read Actions secrets, so its presence and correctness remain unverified until the signed release workflow runs. Never paste the private key into chat, source code, commits or logs. If absent or mismatched, the workflow must stop before publication.

## Required v0.1.5 assets

- `HellsaizPC_AI-update-manifest.json`
- `HellsaizPC_AI-update-manifest.sig`
- `HellsaizPC_AI-windows-x64-full.zip`
- `HellsaizPC_AI-windows-x64-portable.zip`
- `HellsaizPC_AI_Setup.exe`

All five required asset classes were uploaded to the published `v0.1.5` release. The release workflow completed successfully on 2026-11-16.

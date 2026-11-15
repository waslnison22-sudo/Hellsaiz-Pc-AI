# 0.1.4 release readiness

This file is the release gate for the first usable 0.1.4 build. It is intentionally conservative: source code being present is not the same as a Windows installer or in-place update having passed.

## Release scope

The first 0.1.4 build is a local-first Windows desktop assistant, not a finished commercial product.

- Rule-based local commands, allowlisted application control, window/UI Automation, scoped file access, clipboard, reminders, and workflow graph remain available without an LLM.
- LLM is an optional companion provider. The default profile is disabled; local commands must work when no provider is configured or reachable.
- Offline voice paths use local STT/TTS. Downloadable speech models are stored under the user's data directory, not under the version folder.
- Screen OCR is optional and disabled by default.
- Telegram and v2RayTun are optional integrations, disabled until the user configures them.
- Companion work in 0.1.4 is a renderer-neutral foundation only. It does not ship an avatar renderer or proprietary model assets.

## Required release checks

- [ ] Ruff report reviewed and all release-blocking errors fixed.
- [ ] Linux core pytest matrix passes on Python 3.11 and 3.12.
- [ ] Windows full pytest matrix passes on Python 3.11 and 3.12.
- [ ] Windows import diagnostics pass for the desktop, speech, OCR, UI Automation, Telegram, and network modules.
- [ ] PyInstaller desktop, launcher, and updater self-tests pass.
- [ ] Inno Setup installer compiles.
- [ ] Silent install, installed executable self-tests, and silent uninstall pass.
- [ ] The signed manifest verifies against the public key embedded in the updater.
- [ ] Full and portable ZIPs validate against the generated manifest.
- [ ] The actual 0.1.3 portable installation updates to 0.1.4 through the existing 0.1.3 updater.
- [ ] The new 0.1.4 application writes its startup health marker.
- [ ] active.json points to 0.1.4 after the update and the 0.1.3 version directory remains available.
- [ ] User data in LocalAppData is byte-for-byte unchanged.
- [ ] Failure-path integration tests restore 0.1.3 and remove the failed staged version.
- [ ] Final 0.1.4 tag points at the tested release commit; release assets are attached before telling the user to update.

## Observed release blockers (2026-11-15)

### GitHub Actions runner allocation

The CI workflow was retried after separating Ruff into an advisory report. The retry still failed before any job step started.

- Workflow run: 43683154714
- Commit tested: 7e0969ff251485c19dbf03d0c8a0d6d80556b909
- Retry attempt: 2
- All four matrix jobs had runner_id: 0, an empty runner_name, and steps: [].
- The Windows package job was skipped because its test dependency job did not pass.
- No diagnostic artifacts were produced because no runner executed the workflow.

This is a runner allocation/environment failure, not evidence that the source tests passed or failed. Check repository Actions enablement and the account's Actions minutes/billing limits, then rerun the workflow. Do not weaken runtime tests to hide a runner allocation failure.

### Stale v0.1.4 tag

The deleted GitHub Release is not the same as deleting its Git tag. At the last check, refs/tags/v0.1.4 still pointed to commit 6d0baa2f8104b290fe7f4103433e33c504d1dadd, an older OCR metadata-only commit, not the release candidate branch head.

Do not recreate the GitHub Release from that stale tag. After the source passes the release checks, move or recreate the v0.1.4 tag at the exact tested commit, then let .github/workflows/release-windows.yml build and publish the signed assets. The workflow explicitly requires the previous stable release to be v0.1.3 for the first 0.1.4 update acceptance test.

### Signing secret

The release workflow expects the repository Actions secret `HELLSAIZ_UPDATE_SIGNING_KEY`. The GitHub connector available for this session cannot read Actions secrets. Its presence and correctness therefore remain unverified; the Windows release workflow must confirm that the supplied private key matches the public key embedded in the updater before publication. Never paste the private signing key into chat, source code, a commit, or a workflow log. If the secret is absent or mismatched, the build must stop without publishing the release.

## User data and update policy

Do not uninstall 0.1.3 or delete its installation folder when testing the update. Keep the existing root-level HellsaizLauncher.exe and HellsaizUpdater.exe. User data belongs outside versions/<version>/; no release step may overwrite or remove it.

The user-facing 0.1.4 update is ready only after the real Windows release workflow completes successfully and all required assets are visible on the GitHub Release:
- HellsaizPC_AI-update-manifest.json
- HellsaizPC_AI-update-manifest.sig
- HellsaizPC_AI-windows-x64-full.zip
- HellsaizPC_AI-windows-x64-portable.zip
- HellsaizPC_AI_Setup.exe

Until then, remain on the installed 0.1.3 build.

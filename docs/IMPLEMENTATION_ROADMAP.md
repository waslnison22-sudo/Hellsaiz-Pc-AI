# Implementation roadmap

This is the execution order for the next development cycle. Each stage depends on the previous one and must remain independently testable.

## P0 — stabilize existing application

- Keep CI green on Windows/Linux, Python 3.11/3.12.
- Fix lint/test regressions immediately.
- Confirm current SQLite reminders, clipboard operations and workflow scheduler on Windows.
- Add a single-instance app guard and structured health/status reporting. Single-instance locking and speech subsystem diagnostics are implemented.

## P1 — platform foundations

- Create provider, speech, wake-name, theme and automation adapter interfaces. Initial STT, TTS and wake-word adapters are now implemented.
- Add named profiles and capability/health metadata.
- Move secrets into a Windows Credential Manager/DPAPI-backed secret store.
- Keep legacy [llm] and [speech] config migration-compatible.

## P2 — natural-language layer

- Build editable wake-name aliases (Hell, Хелл, Хеллсайз, etc.).
- Build editable phrase/entity catalogs for apps, games, sites and workflows.
- Add deterministic normalization, synonym matching, confidence and ambiguity handling.
- Keep LLM intent fallback optional and behind the same host tool/policy gates.

## P3 — multiple AI and voice engines

- Add Ollama local profile and local OpenAI-compatible profiles for LM Studio and llama.cpp.
- Add a separate GigaChat native adapter with OAuth refresh and provider-specific function-call mapping.
- Add model/feature discovery and tested primary/fallback switching.
- Add selectable STT (Vosk/Whisper.cpp) and TTS (SAPI5/Piper) adapters, configurable primary/fallback switching and multiple user-installed voices. Initial desktop runtime integration is now implemented.

## P4 — Windows control plane

- Add process/window inventory and UI Automation adapter.
- Add focus/window management, scoped keyboard/mouse actions and local OCR.
- Add user-managed app/game catalog and gaming mode workflows.
- Keep strict tool schemas, explicit allowlists and OS constraints; report inaccessible/protected UI without modal per-action confirmations.

## P5 — desktop productization

- Build Windows x64 .exe in GitHub Actions with reviewed PyInstaller spec.
- Add UAC manifest and setup/update strategy.
- Add Task Scheduler auto-start at interactive logon and single-instance behavior.
- Publish workflow artifacts and tagged release assets.
- Ship an onedir Windows package and a stable launcher path. The package already contains separate launcher and updater executables; desktop shortcut creation now targets the stable launcher.
- Complete the signed update manifest, changed-file download, staging, apply-after-exit helper and rollback.
- Keep models, voice packs and optional modules outside the base package; install them on demand.

## P6 — network dependencies and Telegram (later)

- Add v2RayTun installation detection, launch and configured proxy health checks.
- Add startup dependency orchestration.
- Implement a separate Telegram worker with its own token secret, chat allowlist and tool permission matrix only after P1–P5 are stable.

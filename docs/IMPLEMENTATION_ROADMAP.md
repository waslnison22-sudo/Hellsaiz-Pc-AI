# Implementation roadmap — 0.1.4

This roadmap separates source changes from verified release acceptance. A feature is not complete for release merely because its module or UI exists.

## P0 — stability
Implemented: deterministic local command router, single-instance lock, SQLite history, reminders, workflow library/scheduler, app/process allowlists, clipboard/system tools and background-worker cleanup; bounded tool argument size/depth, finite-number validation, side-effect-free registry preflight, strict AI tool-call batches, and read-only system diagnostics for SQLite, workflow graphs, user-data access and disk space, with a 1 MB per-workflow diagnostic read cap.
Still required: real Windows CI on Python 3.11/3.12 and live tests of reminders, clipboard, workflows, shutdown, microphone and TTS; verify the diagnostics worker and GUI signal delivery on Windows.

## P1 — platform foundations
Implemented: provider/speech/wake-name separation, DPAPI-backed secrets, Vosk/Whisper.cpp STT paths, SAPI5/Piper TTS, voice profiles and local command routing.

## P2 — language and intent
Implemented: Russian deterministic intent/slot routes, wake aliases, app aliases, NFKC/casefold plus ё/е normalization, and refusal to guess ambiguous app/window matches. Fuzzy matching is deliberately not used for side-effecting app launches.
Still required: broaden phrase coverage, noisy-ASR tests for every intent and a fuller editable entity catalog.

## P3 — optional AI and voice engines
Implemented: LM Studio, Ollama and llama.cpp OpenAI-compatible profiles; native GigaChat OAuth/function-call adapter; model discovery and provider health; AI tool-call batches capped at 8 calls per response and 16 per user reply, with strict JSON and schema preflight.
Still required: live tests against configured engines and a real GigaChat account; verify primary/fallback behavior and no replay after uncertain tool timeouts.

## P4 — Windows control plane
Implemented: process/window inventory, focus/minimize/maximize/restore/close; UI Automation inspection/click/type with operation-local property snapshots and live visibility/enabled rechecks; scoped keyboard shortcut allowlist; folder-scoped file list/search/read/open; optional creation of new folders/text files without delete/overwrite; optional local Russian OCR.
OCR setup: PP-OCRv5 detection, orientation and Cyrillic recognition models are installed only after explicit user action, checked by SHA-256, then run via ONNX Runtime CPU. OCR stays disabled until models are present and user opt-in is enabled.
Visual foundation: shared monochrome theme module, visible keyboard focus states, accessible navigation label and styled scrollbars.
Still required: live tests in Notepad, Explorer, Settings and a browser; protected/custom UI limitations; Russian OCR checks at different DPI scales and multi-monitor layouts; keyboard-only and Narrator accessibility review.

## P5 — packaging and update
Implemented in source: Windows PyInstaller onedir app, stable launcher/updater, Inno installer, signed manifest, verified extraction, staged apply-after-exit, rollback and data separation; startup task support.
Still required: real Windows package build after the latest dependencies (pywinauto, RapidOCR, MSS, ONNX Runtime), executable self-tests, silent install/uninstall, real update from installed 0.1.3 to 0.1.4, data preservation, health marker and rollback. Verify the signing key matches the updater's embedded public key before publication.

## P6 — network and Telegram
Implemented in source: v2RayTun path selection/launch and local HTTP-proxy health check without global Windows networking changes; optional client auto-launch; separate disabled-by-default Telegram polling worker with DPAPI token, both user/chat allowlists and read-only permission matrix.
Still required: live test of the configured client/proxy and a dedicated Telegram bot/test chat; ensure unauthorized IDs are ignored, stop/start is reliable and proxy failure leaves local voice/commands available.

## P7 — optional animated companion (foundation only)
Implemented: renderer-neutral mode/emotion/viseme contracts, thread-safe state controller, renderer protocol and safe model manifest validation. Architecture research is documented.
Not implemented by design: no avatar, overlay host, Live2D/VRM renderer or character model. This remains optional and must not create another assistant process or separate chat page.

Recommended path: transparent Qt sprite prototype; Piper PCM mouth animation; Live2D Native adapter after SDK/license verification; VRM as a separate renderer.

## Release gate
Do not mark 0.1.4 ready until the latest commit has a real green Windows CI run, all Windows package/install/uninstall checks pass, and the actual 0.1.3 -> 0.1.4 update plus rollback is verified. The latest published stable release remains 0.1.3.

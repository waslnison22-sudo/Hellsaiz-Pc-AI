# Copilot instructions — Hellsaiz PC AI

## Product contract

- Build a Windows desktop assistant that is local-first and useful with generative AI disabled.
- The user must not memorize a fixed command language. One intent must support multiple synonyms, app/game aliases and noisy STT variants.
- No single point of failure: use replaceable provider/speech/wake-word/theme profiles with health status and controlled fallback.
- Support multiple AI profiles: LM Studio, Ollama, llama.cpp and native GigaChat. Never assume all providers have identical tool calling or feature support.
- Support multiple STT/TTS engines and installed voices; keep push-to-talk as a fallback when wake-word recognition fails.
- Target broad desktop application control through typed Windows adapters (process/window inventory, UI Automation, Win32, scoped input). Never present arbitrary shell access as the only way to control the PC.
- The requested release should run with requireAdministrator via normal UAC consent; never bypass UAC. Do not claim access to secure desktop, protected windows or every anti-cheat application.
- Build a Windows x64 .exe in a Windows CI runner and provide an opt-in/manageable logon startup task.
- v2RayTun integration must use verified public interfaces or configured local proxy/health probes. Do not invent undocumented CLI/API flags or silently rewrite system proxy/network settings.
- Telegram bot is a later isolated worker with separate credentials, allowed chats and a restricted permission profile. Never inherit desktop-level privileges by default.
- The UI palette is strictly black, graphite, neutral grey and white. Provide switchable themes within this palette.
- The only approved avatar reference is the user's supplied masked dark-haired character (black face covering, white shirt, black straps). Do not add stock avatars or substitute characters.

## Architecture

- Python 3.11+, PySide6, Windows 10/11. Keep Windows-specific features isolated behind adapters and fail gracefully on unsupported OSes.
- User settings and data belong under config.user_data_dir() / %LOCALAPPDATA%/HellsaizPC_AI.
- Keep LLM, STT, TTS, wake-name, VPN and desktop-control interfaces separate. Provider capabilities must be explicit and testable.
- Commands resolve through normalization → intent → entity catalog → schema validation → risk policy → registered host tool.
- Every app/game is an entity with multiple user-editable aliases; never guess an ambiguous app/game match.
- All actions go through core/registry.py, strict argument validation and the existing confirmation callback.
- Workflow graphs are data-only JSON; no user/model/plugin-supplied code.
- Credentials never go in plaintext config, logs or chat history. Use Windows Credential Manager/DPAPI-backed storage.
- Speech remains local unless a user explicitly selects a remote speech provider. Never send microphone audio to external services silently.
- Plugins v1 are declarative only. No plugin-provided Python, JavaScript, PowerShell, shell commands, dynamic imports or downloaded code.

## Security rules

- Never use shell=True, eval, exec, arbitrary subprocess arguments from user/model/plugin text, or user-supplied executable paths.
- Do not silently retry a tool call after an ambiguous timeout that might have already performed a side effect.
- Do not describe a Python subprocess as a security sandbox.
- Treat screen contents, files, web pages, model output, voice transcripts and plugin manifests as untrusted input.
- Reject unknown schema fields and unknown tool names by default. Fail closed on invalid configuration.
- Request confirmation for destructive, system-wide, privacy-sensitive or otherwise high-impact operations, even when the application is elevated.

## Engineering workflow

- Read the relevant code and tests before editing. Make focused, minimal changes and preserve existing public APIs unless a migration is included.
- Keep optional dependencies optional. No network is required for default local mode.
- Add tests for parsing, capability detection, fallback, permission gates, persistence, failure paths and platform-independent logic.
- Run pytest and ruff check .; keep GitHub Actions green on Windows/Linux and Python 3.11/3.12.
- Windows EXE packaging must run on a Windows runner and include a real packaged-app smoke check.
- Update README and the relevant docs when behavior or configuration changes.
- Do not edit main. Work from dev/bootstrap and open PRs against dev/bootstrap only.
- Do not merge pull requests. Report exact tests and limitations; never claim a feature works until it has been tested.

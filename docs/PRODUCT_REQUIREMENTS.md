# Product requirements — Hellsaiz PC AI

Status: target contract for the next development cycle. Items marked "implemented now" are present in the repository; everything else remains planned until code, tests and a Windows build prove it.

## 1. Product objective

Hellsaiz PC AI is a Windows desktop assistant that understands natural Russian speech and text, controls desktop applications, runs local automations, switches between independent AI and speech engines, and later hosts a separately permissioned Telegram bot.

The user must not learn a fixed command language. One intent can be expressed in many ways, including transcription errors and alternate wake names.

## 2. Mandatory product rules

1. No single point of failure. Speech recognition, speech synthesis, wake-word handling, LLM backends, voice profiles, visual themes and automation providers must be replaceable.
2. Natural-language first. Phrase aliases and synonyms map to intents and entities. Do not make the user remember an exact command.
3. Local-first. The application must start and support useful actions with every AI provider disabled and without Internet.
4. Explicit provider selection and fallback. Show the active provider, model/voice, health state and the reason a fallback occurred. Allow manual switching and an ordered fallback chain.
5. No hidden retry of uncertain side effects. If a provider or tool times out after a side effect may have started, do not replay it automatically. Report uncertainty and let the user decide.
6. User data stays local unless a selected remote provider needs the request. Remote providers are opt-in per profile. Never silently send microphone recordings, screen contents or files to an API.
7. All desktop actions go through typed host tools and a policy gate. A model, phrase alias or future bot must never execute arbitrary shell/script text.
8. Every control in the UI must work. No placeholder buttons presented as implemented functionality.

## 3. Speech and wake-name profiles

Keep separate settings for:

- Input engine (STT): Vosk, whisper.cpp, and future local engines. Each adapter reports availability, language/model, latency and error state.
- Wake-name resolver: a configurable alias list. Initial Russian/English aliases include: Хелл, Хеллсайз, Хелсайз, Hell and Hellsaiz. Matching must tolerate case, punctuation, spacing and plausible STT spelling variants. Aliases must be editable.
- Optional wake-word engine: a replaceable always-listening engine. This is separate from phrase normalization; a transcript alias list is not itself an acoustic wake-word detector.
- Output engine (TTS): SAPI5 installed voices (including RHVoice voices exposed through SAPI), Piper, and future offline engines. Enumerate voices, show test playback, and permit a fallback voice.
- Speaking profile: selectable voice, rate, volume, response style and verbosity. A visual theme is a separate profile and must not be coupled to a voice.
- Health/fallback: a missing model, unavailable microphone, failed TTS engine or missing voice must be visible. A configured fallback is attempted without losing the user's original selection.

A push-to-talk path remains available even when a wake-word engine is disabled or broken.

## 4. Natural-language intent and entity resolution

The command pipeline should be layered:

1. Normalize transcript/text (case, punctuation, whitespace, wake aliases and common transcription variants).
2. Resolve a known intent from phrase aliases and patterns.
3. Resolve the entity from a user-editable catalog (applications, games, folders, sites and workflow profiles).
4. Validate arguments against the host tool schema.
5. Apply the risk policy and request confirmation when required.
6. Execute through the registered tool; display what was understood and what was done.
7. Use an enabled LLM as a fallback for ambiguous/unmapped language, not as permission to execute arbitrary code.

Many expressions must point to the same intent/entity. For example, "открой Steam", "запусти Steam", "игровой режим" and "открой игры" may map to a user-configured gaming profile; "запусти кску", "запусти CS", "запусти CS:GO" and "запусти CS2" must be separate catalog entries where the user has installed those games. Do not assume an executable path: discover the app/window through supported OS APIs or let the user select it once.

If confidence is low or two entities match, ask one concise clarification instead of launching the wrong application. Phrase aliases and entity aliases must be editable in the UI and persisted locally.

## 5. AI provider profiles

The application must expose multiple independent provider profiles and a manual/automatic selection policy.

Required provider families:

- LM Studio: local OpenAI-compatible server, commonly http://127.0.0.1:1234/v1.
- Ollama: local server; its OpenAI-compatible endpoint is commonly http://127.0.0.1:11434/v1. Treat compatibility as a supported subset and probe tool/function-call capability per model.
- llama.cpp server: local OpenAI-compatible endpoint, configurable by the user.
- GigaChat API: native Sber adapter with OAuth token refresh and native function-calling request/response mapping. Do not assume its functions/function_call wire format is identical to OpenAI tools.
- Future providers: addable through the provider interface without changing orchestration, tool security or the UI's overall selection model.

Provider behavior:

- Store multiple named profiles; each profile has provider type, endpoint, model, timeout, enabled features and a priority.
- Provide test connection, list/refresh models where the provider supports it, provider health, latency and feature support (streaming, tools, vision, JSON).
- Support primary, fallback and manual-only profiles.
- If a model does not support tools, the app must disable that feature for that profile or use deterministic command routing; do not pretend tool calls work.
- Never retry a possibly executed tool call because an API response was lost.
- API credentials must not be written in plaintext to config files, logs, crash reports or chat history. Use Windows Credential Manager/DPAPI-backed storage; redact secrets from UI logs.
- Remote APIs are disabled until the user enters credentials and explicitly enables the remote profile.

## 6. Desktop and application control

The goal is broad control of installed and running desktop applications, not an unrestricted command shell.

Required capabilities, added incrementally and through typed tools:

- enumerate running processes and visible top-level windows;
- identify an application by process/window title and user-defined aliases;
- focus, switch, minimize, maximize, restore and close a window;
- launch applications from a user-approved app catalog;
- inspect accessible UI controls using Windows UI Automation;
- click controls, type text and send keyboard shortcuts only to a selected target window;
- use Win32 and controlled mouse/keyboard automation as a fallback when accessibility metadata is unavailable;
- take a screenshot and use local OCR/vision only when the user has enabled the relevant provider;
- manage files and folders through typed operations with path validation and preview;
- expose clear confirmation for destructive actions (delete, overwrite, terminate process, system settings).

"Control any app" is a best-effort product goal, not a promise to bypass Windows security boundaries. Applications with custom rendering, anti-cheat, protected processes, secure desktop/UAC prompts, locked sessions or inaccessible controls may reject automation. Report the limitation instead of faking success.

## 7. Administrator execution model

The requested Windows release should declare requestedExecutionLevel=requireAdministrator, so Windows displays its normal UAC consent/credential prompt when required. The program must never bypass UAC, self-elevate silently or modify UAC policy.

Run-level elevation is not equivalent to unlimited system control. Keep explicit action permissions and confirmations even when elevated. Do not set uiAccess=true unless a separately signed and installed accessibility component meets Microsoft's UIAccess requirements; do not claim that an elevated process can automate the secure desktop or protected UI.

## 8. EXE, release and startup

- Build the Windows x64 application in a Windows GitHub Actions runner; Linux CI must not be treated as a Windows build.
- Produce a versioned .exe package using a maintained packaging pipeline (initial candidate: PyInstaller with a reviewed spec file and Qt data/plugin collection).
- Publish the executable as a workflow artifact for every main development build and as a GitHub Release asset for tagged versions.
- Include all required runtime libraries and license notices. Do not bundle private user models, voice packs, API keys or VPN credentials.
- Provide an installer/setup action that registers auto-start at interactive user logon through Windows Task Scheduler with the intended highest run level. The user can disable it in Settings.
- Auto-start must be idempotent: no duplicate tasks or duplicate app instances. A single-instance lock should bring the existing window to the front.
- Background services and Telegram worker are separate from the desktop UI lifecycle.

## 9. v2RayTun and future Telegram bot

v2RayTun integration:

- Detect whether v2RayTun is installed/running, allow the user to select its Windows executable, launch it when requested, and show a separate connection/health state.
- Do not invent private APIs, undocumented command-line flags or hidden config-file formats.
- The upstream public repository identifies a separate Windows x64 desktop client, but its public README does not document a CLI/API for toggling the tunnel. Start/health integration must therefore be implemented using a verified public interface or a user-configured local proxy/health probe. The first safe fallback is to open the application and ask the user to connect manually.
- Do not silently rewrite the global Windows proxy, routes, DNS or VPN configuration. Make any system-wide networking change a separate explicit user-approved action.
- Provide a startup dependency state machine: app ready → v2RayTun present/launched → configured proxy/tunnel health verified → dependent worker may start. A failed VPN check must not start the Telegram worker.

Telegram bot (later milestone):

- Run the bot in a separate local worker/service, not inside the UI thread.
- Start only when its settings enable it and the configured network route is healthy.
- Its settings will include a Telegram bot token, allowed chats/users, provider selection and a per-tool permission matrix. A bot token is a secret and must be stored using the Windows secret store.
- The bot must use a separate restricted tool profile. Do not inherit the desktop user's full computer-control permissions by default.
- The user explicitly said this module is for a later phase; prepare the interfaces now, but do not implement the bot before the desktop/provider foundation is stable.

## 10. Appearance and interaction profiles

- Support multiple visual themes, not a single hardcoded skin. Initial built-in themes may stay monochrome (dark graphite, pure black, light neutral).
- Save theme separately from assistant voice/personality.
- Support multiple assistant response profiles (for example concise, detailed, neutral), user-editable later.
- Theme, voice, wake aliases and provider profiles must be switchable without reinstalling the application.

## 11. Verification and acceptance

- Every adapter must have a health check and a stable status/error result.
- Test provider switching, unavailable-primary fallback, unavailable-secondary behavior, credential redaction, tool-capability detection and timeout safety with mocked endpoints.
- Test phrase alias normalization and entity resolution, including noisy STT variants and ambiguous matches.
- Test application catalog matching and argument validation without actually launching processes in unit tests.
- Test elevation-manifest contents and startup-task registration through a mockable adapter; do not require admin rights in ordinary CI tests.
- Test v2RayTun detection/proxy health using mocks; never require a VPN in CI.
- Continue running pytest and ruff check . on Windows/Linux and Python 3.11/3.12.
- A feature is complete only when the UI, persistence, error/fallback path, tests and documentation are present.


## 12. Personal HUD and media library (0.1.4)

- This is a private, single-user Windows application. No public marketplace, user accounts, telemetry, or shared voice/wallpaper uploads are part of the design.
- Main window: Windows-native title bar, permanent glass sidebar, transparent graphite workspace surfaces, cool white controls and an optional user-owned wallpaper. The default background is plain black.
- Wallpapers: import local PNG/JPG/WEBP/BMP/GIF, store a private copy under the user data directory, validate the format and size, and support GIF playback. Reset restores pure black.
- Voices: Windows SAPI5 remains available. Piper is an optional offline neural TTS backend. The app downloads model, config and MODEL_CARD into local user storage, displays model-card license, and allows model selection and playback testing.
- The 3D assistant character is postponed. It is not required for the 0.1.4 core.
- Natural-language command handling follows an intent-and-slot design inspired by voice-assistant skill systems: classify the request first, then extract parameters and invoke a deterministic local skill or an explicitly online information skill.

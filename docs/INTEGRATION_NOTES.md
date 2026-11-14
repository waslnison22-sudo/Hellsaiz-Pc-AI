# Integration notes — verified 2026-11-14

This document records external integration facts used to shape the architecture. It is not a claim that the integrations are implemented.

## GigaChat API

- Current Sber developer documentation states that new GigaChat API connections use https://api.giga.chat from 2026-07-17. The legacy gigachat.devices.sberbank.ru URL remains available for existing connections but is not the new connection target.
- Authentication obtains an access token through the documented OAuth endpoint. The docs state that an access token is valid for 30 minutes; the adapter must refresh before expiry and handle 401 safely.
- Function calling is documented via the GigaChat functions array and function_call mode. Do not assume the native request/response format is identical to the OpenAI tools field. Convert the host's internal tool descriptors to/from the provider-specific format.
- Keep TLS certificate validation enabled. Never copy examples that disable certificate verification into production code.

Official sources:
- https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/gigachat-api
- https://developers.sber.ru/docs/ru/gigachat/guides/functions/overview
- https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/post-chat

## Ollama

- Ollama documents a local API at http://localhost:11434/api and an OpenAI-compatible endpoint at http://localhost:11434/v1.
- The OpenAI-compatible implementation is a subset, so the client must probe or track model/provider support rather than assume every OpenAI feature works.
- Its current OpenAI compatibility documentation lists tool support for /v1/chat/completions.

Official sources:
- https://docs.ollama.com/api
- https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx

## v2RayTun

- The official upstream repository is LXST-CODE/v2RayTun. Its README describes platform-specific apps and a separate Flutter/Dart desktop codebase for Windows/Linux. Windows support is x64 and Windows 10+.
- The public README lists Windows downloads and releases, but does not document a CLI or API for controlling tunnel state. Do not invent command flags or reverse-engineer an unsupported control surface as an assumed integration.
- Initial integration should detect/launch the selected client and verify a user-configured local proxy/health endpoint. Tunnel connection remains manual until a supported control interface is verified.

Sources:
- https://github.com/LXST-CODE/v2RayTun
- https://github.com/LXST-CODE/v2RayTun/tree/main/windows
- https://github.com/LXST-CODE/v2RayTun/releases

## Windows elevation and UI automation

- Windows application manifests can declare requireAdministrator, causing UAC to request consent/credentials. This does not bypass UAC.
- Microsoft recommends that most desktop apps use asInvoker and request elevation only when truly necessary. This project has a user requirement for elevated launch, so the release manifest is planned as requireAdministrator, but the larger attack surface must be constrained by the action policy.
- Windows UI Privilege Isolation (UIPI) can prevent automation from crossing integrity levels. UAC secure desktop and protected windows are not ordinary automation targets.

Official sources:
- https://learn.microsoft.com/ru-ru/windows/win32/sbscs/application-manifests
- https://learn.microsoft.com/ru-ru/windows/win32/secbp/running-with-administrator-privileges
- https://learn.microsoft.com/en-us/troubleshoot/power-platform/power-automate/desktop-flows/ui-automation/uipi-issues
- https://learn.microsoft.com/en-us/power-automate/desktop-flows/how-to/enable-ui-access

## Windows EXE packaging

- PyInstaller supports bundling the Python interpreter and dependencies into a folder or a single executable. A reviewed spec file is the place to include Qt plugin/data assets where automatic discovery is insufficient.
- Build Windows artifacts on Windows runners and validate the packaged executable with a smoke test. Do not assume Linux can cross-compile a Windows EXE.

Official sources:
- https://pyinstaller.org/en/stable/operating-mode.html
- https://pyinstaller.org/en/stable/spec-files.html

# Copilot instructions — Hellsaiz PC AI

## Product contract
- Build a Windows desktop assistant that is local-first and useful with generative AI disabled.
- The default runtime must not require network access, paid APIs, cloud accounts, or a running LLM.
- Optional local LLM support must remain opt-in. Never make LM Studio, llama.cpp, or a remote endpoint mandatory.
- The UI palette is strictly black, graphite, neutral grey, and white. Do not introduce red or other saturated accent colors.
- The only approved avatar reference is the user's supplied masked dark-haired character (black face covering, white shirt, black straps). Do not add stock avatars, female models, or substitute characters.

## Architecture
- Python 3.11+, PySide6, Windows 10/11. Keep Windows-specific features isolated behind adapters and fail gracefully on unsupported OSes.
- User settings and data belong under config.user_data_dir() / %LOCALAPPDATA%/HellsaizPC_AI.
- Commands are deterministic rules in core/commands.py and execute through core/registry.py.
- Windows actions must use registered tools, local allowlists, strict argument validation, and the existing confirmation callback. Do not bypass these layers.
- Workflow graphs are data-only JSON validated by workflows/graph.py. The runner may execute only known node types and registered tools.
- UI-only workflow node coordinates belong in the workflow layout sidecar, not inside workflow behavior/configuration.
- Speech engines are optional local adapters. Never send microphone audio to external services.
- Plugins v1 are declarative only. Do not execute plugin-provided Python, JavaScript, PowerShell, shell commands, dynamic imports, or downloaded code.

## Security rules
- Never use shell=True, eval, exec, arbitrary subprocess arguments from user/model/plugin text, or user-supplied executable paths.
- Do not add process, file, browser, registry, keyboard, or mouse automation unless it goes through a narrowly scoped host tool with explicit user consent and tests.
- Do not describe a Python subprocess as a security sandbox. Document the actual boundary.
- Treat screen contents, files, web pages, model output, and plugin manifests as untrusted input.
- Reject unknown schema fields and unknown tool names by default. Fail closed on invalid configuration.

## Engineering workflow
- Read the relevant code and tests before editing. Make focused, minimal changes and preserve existing public APIs unless migration is included.
- Keep optional dependencies optional. Do not add a dependency to the base install if a lazy adapter or an extra will work.
- Add unit tests for parsing, validation, permission gates, persistence, failure paths, and Windows-independent logic.
- Run pytest and ruff check .; keep GitHub Actions green on Windows/Linux and Python 3.11/3.12.
- Update README and config/default.toml when behavior or configuration changes.
- Do not edit main. Work from dev/bootstrap and open pull requests against dev/bootstrap only.
- Do not merge pull requests. Report exactly what was implemented, tests that actually ran, and limitations.

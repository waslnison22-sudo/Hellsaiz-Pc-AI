# Local speech provider routing

Hellsaiz PC AI keeps speech recognition local. STT engines implement the
`Transcriber` protocol in `hellsaiz_pc_ai.speech.stt` and are selected by
`SpeechRouter`.

The router supports one explicit primary engine and an optional local fallback.
A successful result identifies the actual engine; a fallback result also
contains the primary failure reason so the UI can report why the configured
engine was not used. The router does not upload audio, change configuration,
or retry any desktop action.

Existing adapters:

- `VoskTranscriber`: offline Russian recognition with a local model.
- `WhisperCppTranscriber`: offline whisper.cpp CLI adapter.

The desktop voice button uses this router. Primary and fallback providers,
model paths and recording duration are configurable under Settings → Speech
Recognition and stored in the local assistant profile. Vosk and whisper.cpp
remain local engines; no cloud speech endpoint is used.

TTS uses `SpeechOutputRouter` to try the preferred voice engine and then one
local fallback. SAPI5 and Piper are currently supported. A fallback is logged
with the reason the preferred voice failed.

## Hands-free activation

`WakeWordListener` is an optional Vosk-based microphone loop. It is off by
default and can be enabled from Settings. It detects configured wake aliases
at the start of an utterance, then accepts the next utterance as the command;
when the wake alias and command occur in one utterance, it dispatches the tail
immediately. Microphone blocks are held in a bounded in-memory queue and are
not written to disk. The listener is paused while the assistant processes and
speaks a command, then resumes when the response completes. Push-to-talk
remains available independently of hands-free mode.

Hands-free activation requires the local Vosk model and the optional `voice`
dependencies. If the model or microphone is unavailable, the setting is
turned off and the error is shown in the settings page.

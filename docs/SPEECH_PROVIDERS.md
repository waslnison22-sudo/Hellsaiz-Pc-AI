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

The router is an independent foundation. The desktop capture flow still needs
to be wired to user-selectable STT profiles before fallback can be configured
from the settings UI. No wake-word listening is implied by this feature.

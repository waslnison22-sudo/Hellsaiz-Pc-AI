# Optional Desktop Companion — architecture and implementation research

Status: FOUNDATION ONLY. The current desktop application does not show an avatar and does not load a renderer. The companion remains optional and must not become the assistant's core.

## Desired UX

- One local assistant process; no companion service or second executable.
- A transparent, frameless desktop surface containing only the character: no title bar, page, navigation, chat panel or opaque card.
- The existing Hellsaiz PC AI window remains the settings/chat surface. The character is a visual companion, not a separate conversation client.
- Dragging, position lock, size, opacity, hide/show and model selection are context actions, not a separate UI page.
- Renderer failure hides the character and must not affect voice, commands, reminders, workflows or the main application.
- No webcam or emotion recognition. Expressions come only from assistant events and TTS output.

A desktop overlay is a native widget surface, but it does not need to look like a conventional window. Qt's Windows documentation requires WA_TranslucentBackground and FramelessWindowHint for a translucent top-level widget. Set the attribute before showing the widget. See [Qt QWidget — Creating Translucent Windows](https://doc.qt.io/qt-6/qwidget.html).

## Separation of concerns

1. Assistant core emits semantic events: idle, listening, thinking, speaking, error.
2. Emotion mapper maps explicit response metadata to neutral, happy, sad, surprised, angry, confused or curious.
3. Speech synchronizer maps TTS output to a mouth-open envelope or A/I/U/E/O visemes. It consumes output audio, not the microphone recording.
4. Renderer adapter loads a supported model and applies a normalized snapshot. It cannot call the LLM, execute tools, capture audio or read secrets.
5. Overlay host owns the transparent surface and lifetime in the existing process/event loop.
6. Model package manager validates a manifest, referenced assets and relative paths. It never imports or executes scripts from a model folder.

The current Python package hellsaiz_pc_ai.companion provides normalized modes, emotions, visemes and snapshot validation; a thread-safe snapshot controller; a renderer protocol; and model manifest validation with path-traversal checks. These are contracts only. There is no renderer, avatar file or animation in 0.1.4.

## Supported model families

| Format | Purpose | Animation data | Status |
|---|---|---|---|
| Live2D Cubism | Illustrated 2D character | Rig parameters, motions, expressions, physics, lip-sync | Recommended first production renderer |
| VRM 1.0 | 3D humanoid character | Standard emotions, vowel mouth shapes, blink, gaze | Future adapter |
| Sprite/PNG sequence | Lightweight 2D prototype | Pre-rendered idle/listening/thinking/speaking states | Best overlay prototype |
| Custom adapter | Other user-owned formats | Adapter-defined | Extension point |

“Any model” means any format with a supported renderer adapter. A model file by itself cannot animate; it needs compatible art/geometry, textures, rig/parameters and motion data. Arbitrary model files and their scripts must never be executed.

## Recommended renderer: Live2D Cubism

For the requested illustrated desktop character, Live2D Cubism is the strongest first production candidate.

- The official platform support matrix, updated 2026-09-29, lists Windows Native support for OpenGL, DirectX 11 and Vulkan. This does not require CUDA or an NVIDIA GPU.
- Live2D's official Native SDK is implemented in C++; it is distributed separately from this repository.
- Cubism lip-sync uses model parameters. MotionSync can map audio to viseme-style mouth movement, subject to the SDK package and MotionSync Core.
- The SDK and Core are not regular open-source Python dependencies. Do not bundle proprietary SDK files or download them silently.

References:
- [Live2D SDK platform support](https://docs.live2d.com/en/cubism-sdk-manual/platform/)
- [Live2D Cubism SDK overview and Native SDK](https://www.live2d.com/en/sdk/about/)
- [Live2D lip-sync parameter mapping](https://docs.live2d.com/en/cubism-sdk-manual/lipsync/)
- [Live2D MotionSync Plugin](https://www.live2d.com/en/sdk/download/motionsync/)

### Recommended integration route

1. Prototype the overlay with a small sprite renderer and transparent Qt widget. This validates transparency, hit testing, DPI, multi-monitor placement and lifecycle without a proprietary SDK.
2. Implement Live2D Cubism Native as a renderer adapter in the same application process, using DirectX 11 or OpenGL. Keep the model and SDK in an optional component.
3. Add mouth motion from Piper PCM first; add explicit visemes/MotionSync when SDK licensing and model parameters are confirmed.
4. Add VRM as a separate renderer adapter, not as a rewrite of the companion controller.

A Qt WebEngine/Three.js renderer is technically possible, but adds a sizeable WebEngine runtime and another rendering layer to the Windows package. Prefer native Live2D for the first production renderer.

Before any redistribution, verify the current Live2D SDK terms and each model creator's license. Keep user-owned models and proprietary SDK components outside the core update package.

## VRM 1.0

VRM 1.0 specifies preset emotion expressions (happy, angry, sad, relaxed, surprised), vowel mouth expressions (aa, ih, ou, ee, oh), blink and gaze. This maps cleanly to the neutral companion contract.

References:
- [VRM 1.0 expressions](https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/expressions.md)
- [VRM 1.0 specification](https://github.com/vrm-c/vrm-specification/tree/master/specification/VRMC_vrm-1.0)

## Speech and expression state mapping

- Listening: attentive pose and subtle gaze motion.
- Thinking: neutral/curious pose.
- Speaking: mouth envelope from outgoing TTS audio; use explicit viseme events if available.
- Finished response: return to idle.
- Error: brief confused state, then idle.

For a Live2D model, map visemes/envelope to that model's actual mouth parameter IDs. For VRM, map to aa/ih/ou/ee/oh. Do not assume every imported model has every parameter. The adapter must advertise supported features.

## Reliability and privacy

- Companion disabled: no renderer initialization, model loading, screen capture, microphone capture or GPU initialization.
- Renderer crash: hide it, log a safe diagnostic and keep the assistant alive.
- No webcam, screen capture or remote API for emotion detection.
- Use the same in-process event bridge as the assistant; no separate LLM or bot.
- Test AMD graphics, DPI, monitor changes, sleep/resume, focus, drag and click-through behavior.
- A fully click-through window cannot also be dragged; use a small drag region or user-toggle.

## Implementation stages

1. Sprite renderer and transparent overlay host.
2. Audio-envelope mouth animation using Piper PCM.
3. Live2D Native adapter once SDK package/license path is confirmed.
4. VRM adapter.
5. Model import/library UI, metadata/license display and lifecycle cleanup.

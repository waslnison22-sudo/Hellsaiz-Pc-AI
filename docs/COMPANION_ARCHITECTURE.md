# Optional Desktop Companion — architecture proposal

Status: **foundation only**. The companion is deliberately disabled by default and is not required to start, speak, route commands, use reminders, or update the app.

## Product behavior

- The companion is an optional transparent character overlay, not a separate chat page and not a second assistant process.
- The existing chat remains the control panel. In the eventual desktop mode the character is drawn directly over the desktop/main application surface without a title bar, frame, background panel, or separate navigation page.
- A small transparent hit region should allow dragging the character. A context menu may expose hide/show, lock position, size, opacity, and model selection.
- The companion must be possible to disable completely. Disabling it must release renderer resources and must not change the assistant's normal operation.

A desktop overlay is still implemented through a native window/widget surface. On Windows, Qt documents transparent painting via `WA_TranslucentBackground`; top-level transparent widgets also need `FramelessWindowHint`. The attribute should be set before the surface is shown, not toggled later.

## Separation of concerns

1. **Assistant core** emits semantic state changes: idle, listening, thinking, speaking, error.
2. **Emotion mapper** maps optional response metadata and speech events to a renderer-neutral emotion.
3. **Speech synchronizer** maps audio timing or phoneme/viseme events to mouth poses. The first version should support amplitude-based mouth opening; a better renderer adapter can use explicit A/I/U/E/O visemes when its TTS engine supplies alignment.
4. **Renderer adapter** loads and draws a model and applies a normalized snapshot. It must not call the LLM, execute tools, capture microphone input, or access secrets.
5. **Overlay host** owns the transparent surface and lifetime. It may be parented to the main application window initially; a desktop-pinned mode can use an owned, borderless top-level surface while remaining in the same process and UI system.

The Python contracts in `hellsaiz_pc_ai.companion` establish the normalized states, thread-safe event bridge, renderer protocol, and validated model manifest. No third-party model code is imported dynamically. Future renderers must be explicitly registered by the application.

## Model formats

| Format | Use | Animation support | Role |
|---|---|---|---|
| Live2D Cubism | 2D illustrated/anime character | Parameters, motions, expressions, physics and mouth/eye control from authored model data | Best first candidate for a polished 2D companion |
| VRM 1.0 | 3D humanoid avatar | Standard expressions, blink, gaze, vowel mouth shapes and spring bones | Optional 3D adapter |
| Sprite/PNG sequence | Lightweight 2D fallback | Pre-rendered idle/listening/thinking/speaking/emotion states | Lowest setup cost and safest starter |
| Custom adapter | User-provided future formats | Adapter-defined | Extension path without changing assistant core |

“Any model” means any supported format with a renderer adapter, not any arbitrary file. The app should validate a model package and its referenced assets; it must not execute scripts shipped inside untrusted model folders.

## Renderer recommendation

For the requested illustrated companion, start with **Live2D Cubism** as the first production renderer. The official Web SDK is written for WebGL and has a reusable framework; the Native SDK supports Windows graphics APIs including DirectX 11 and OpenGL. The actual model is exported from Cubism Editor (for example `.moc3` plus `.model3.json` and texture assets). The Cubism Core binary is distributed within the official SDK package and is not an ordinary open-source GitHub dependency.

For later 3D support, use **VRM 1.0** through a renderer such as Three.js + three-vrm. VRM standardizes facial expressions including emotions, blink and A/I/U/E/O mouth shapes, plus gaze controls. This is a clean match for the normalized emotion/viseme contract already prepared here.

A sprite renderer is a useful first visible prototype if Live2D SDK integration or model licensing delays the 2D renderer. It can share the same companion state bridge.

## Animation and speech synchronization

- Listening: attentive expression, subtle eye/gaze motion.
- Thinking: neutral/curious expression, optional small idle motion.
- Speaking: mouth-open envelope driven by the outgoing audio; use explicit visemes when phoneme timing is available.
- Completed response: restore idle expression, optionally add a short happy/neutral response.
- Error: brief confused expression, then return to idle.

The avatar must never infer facial emotion from private webcam input by default. All expressions are driven by explicit app events and the selected TTS output only.

## Windows/Qt overlay constraints

- Set `WA_TranslucentBackground` before showing the widget; use a frameless window flag for top-level transparent mode.
- Use an owned Qt surface and lifecycle tied to the main application. Do not launch a separate companion executable.
- Keep rendering and animation off the assistant's command/voice worker. A renderer failure should hide the character and log the issue without taking down the application.
- Test multi-monitor coordinates, DPI scaling, display changes, sleep/resume, focus behavior and hit testing.
- Make desktop click-through optional. A fully click-through surface cannot also be dragged; use a user-toggle or a narrow draggable area.

## Licensing and packaging

Live2D's SDK download is governed by its SDK agreements. Live2D states that publication licensing applies when content using its SDK is released; individual/small-scale exemptions and special Expandable Application cases are defined on its license page. Before redistributing the application or any model, re-check the current terms and the model creator's license. The private local prototype should keep SDK binaries and character model assets in an optional user-selected component rather than silently bundling or downloading them.

VRM model packages also retain their creator's own license and attribution requirements. The application should show the model's metadata/license information before enabling an imported model when available.

## Planned implementation stages

1. Build a sprite renderer and transparent overlay host for one local model.
2. Add the Live2D adapter after confirming SDK version, model export and licensing path.
3. Add audio-envelope mouth movement; later map phoneme/viseme events.
4. Add VRM adapter as an independent renderer.
5. Add model library/import UI only after the rendering, validation and user-data lifecycle are stable.

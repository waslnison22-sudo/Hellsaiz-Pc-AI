# Engineering notes — reliability, Windows UI and assistant mechanics

Updated: 2026-11-15

This note separates external platform guidance from the implementation choices made in Hellsaiz PC AI. The references describe platform behavior; they do not certify this application's runtime.

## 1. Qt threading and responsive desktop UI

**External guidance**

Qt documents that QWidget and other GUI classes must be used only in the main thread. Long-running work should happen in a worker thread and results should return to the GUI through signals/slots. QObject instances have thread affinity; cross-thread direct access is unsafe unless properly synchronized.

References:
- https://doc.qt.io/qtforpython-6/overviews/qtdoc-threads-qobject.html
- https://doc.qt.io/qt-6/qthread.html

**Application decision**

- Keep all widgets, text updates, dialogs and pixmap work in the GUI thread.
- Use worker signals for downloads, provider checks, speech and other blocking work.
- Treat one-shot blocking tasks and long-lived event-driven services differently. A future migration to QObject worker objects moved to QThread is appropriate when a task needs its own event loop, timers or sockets; do not refactor every working one-shot worker without a specific benefit.
- Stop and join background work within bounded shutdown windows; never silently abandon a worker that owns microphone, network or model resources.

## 2. Windows UI Automation reads and stale elements

**External guidance**

Microsoft explains that retrieving UI Automation properties one-by-one can require repeated cross-process calls. Native UI Automation CacheRequest can batch selected properties and control patterns. Cached data is a snapshot and becomes stale when the UI changes; clients must obtain a fresh snapshot after relevant changes.

References:
- https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-clientsoverview
- https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-cachingforclients

**Application decision in this iteration**

- Collect each named control's identifying properties once per operation and reuse that local snapshot for matching and display.
- Before click or text entry, recheck that the selected control is still visible and enabled. If it changed, abort instead of acting on a stale match.
- This is an operation-local Python snapshot, not a native COM IUIAutomationCacheRequest. Native bulk caching and UIA event-driven invalidation remain a separate optimization to research with pywinauto/backend constraints and Windows integration tests.

## 3. AI tool-call boundary and bounded execution

**Implementation**

- Validate the complete provider tool-call batch before executing any handler.
- Maximum 8 calls in one model response and 16 calls across one user reply.
- Require unique, non-empty call IDs and a non-empty function name.
- Limit serialized argument JSON size before parsing.
- Reject malformed JSON, duplicate object keys, non-standard numeric constants, oversized values and non-object arguments before side effects.
- The ToolRegistry applies a second schema/type/depth/collection validation gate before invoking each registered handler.

**Rationale**

The tool-call limit is separate from the model round limit. A provider response may contain multiple calls in one round; a round limit alone does not bound the number of side effects. Batch validation avoids executing the first items when a later item in the same batch is malformed.

## 4. Deterministic language handling for side effects

**Engineering decision**

- Normalize Unicode compatibility forms, case, whitespace and common Russian ё/е variation before deterministic intent matching.
- Keep exact patterns, explicit aliases and allowlists for side-effecting actions.
- Do not introduce fuzzy matching that could turn an uncertain transcript into an unintended app launch, click or file operation.
- Use clarification or a clear not-in-allowlist result when an entity is unknown or ambiguous.

## 5. Interface clarity and accessibility

**Implementation**

- Shared dark monochrome styles are separated into app/theme.py.
- Main navigation exposes an accessible name and description.
- Keyboard focus is visible on navigation, buttons and input controls.
- Scrollbars and tooltips use the same restrained graphite/white visual language.

**Still to verify**

- Windows Narrator and keyboard-only navigation on a real Windows session.
- High-DPI layouts, display scaling and multi-monitor geometry.
- Focus contrast and reduced-motion preferences.
- Responsive behavior on smaller laptop windows.

## 6. Next mechanics to investigate

1. Native UIA CacheRequest and UIA event subscriptions, with cache invalidation rather than holding stale controls.
2. Qt QThreadPool/QRunnable for short independent background operations, while keeping long-running listeners separately managed.
3. A central diagnostics model that reports provider, microphone, STT, TTS, OCR, proxy and Telegram health without mixing optional failures with core local-command availability.
4. Accessibility validation as part of UI acceptance, not only visual inspection.
5. A typed capability/permission layer for future plugins, preserving the existing allowlist and argument-schema gate.

These investigations must be followed by unit tests and Windows integration checks before being marked complete.

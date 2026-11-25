"""Legacy HTML bubble rendering for the old QTextEdit transcript.

Kept for compatibility (tests and any HTML export); the live chat now renders
widgets from :mod:`hellsaiz_pc_ai.app.chat_page` (MessageBubble).
Pure data: no Qt imports here so tests can run without a QApplication.
"""

from __future__ import annotations

import html
import re

ASSISTANT_NAME = "Hellsaiz"


def _escape(text: str) -> str:
    return html.escape(str(text), quote=False)


_CODE_STYLE = (
    "font-family:Consolas,'Courier New',monospace; background:rgba(255,255,255,20);"
    " padding:1px 4px; border-radius:4px;"
)


def _inline_markup(escaped: str) -> str:
    """Apply **bold** and `code` to already escaped text."""
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    return re.sub(
        r"`([^`]+)`",
        lambda match: f'<span style="{_CODE_STYLE}">{match.group(1)}</span>',
        escaped,
    )


def render_assistant_text(text: str) -> str:
    """Small, safe markdown subset for assistant bubbles.

    Supports **bold**, `inline code` and "- " bullet lists. Anything else is
    escaped and rendered literally, so model output cannot inject HTML.
    """
    blocks: list[str] = []
    paragraph: list[str] = []
    bullets: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append("<br>".join(_inline_markup(line) for line in paragraph))
            paragraph.clear()

    def flush_bullets() -> None:
        if bullets:
            blocks.append(
                "<ul>"
                + "".join(f"<li>{_inline_markup(item)}</li>" for item in bullets)
                + "</ul>"
            )
            bullets.clear()

    for raw_line in _escape(text).split("\n"):
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            flush_paragraph()
            bullets.append(stripped[2:])
            continue
        flush_bullets()
        if not stripped:
            flush_paragraph()
            continue
        paragraph.append(raw_line)
    flush_bullets()
    flush_paragraph()
    return "".join(blocks)


def chat_bubble_html(role: str, text: str) -> str:
    """Render one chat message as a styled HTML fragment.

    Roles:
        "assistant"  — accent-barred bubble with the assistant name.
        "user"       — neutral glass bubble.
        "recognized" — dim one-line transcript note (speech recognition).
    Any other role renders as a plain paragraph.
    """
    safe = _escape(text).replace("\n", "<br>")
    if role == "assistant":
        return (
            '<div style="border-left:3px solid #E8C29E; background:#171716;'
            ' padding:8px 12px; border-radius:10px; margin-top:6px;">'
            f'<span style="color:#E8C29E;"><b>{ASSISTANT_NAME}:</b></span> '
            f"{render_assistant_text(text)}</div>"
        )
    if role == "user":
        return (
            '<div style="background:#171716; border:1px solid rgba(255,255,255,15);'
            ' padding:8px 12px; border-radius:10px; margin-top:6px;">'
            '<span style="color:#A6A29C;"><b>Вы:</b></span> ' f"{safe}</div>"
        )
    if role == "recognized":
        return (
            '<p style="color:#A6A29C; font-size:11px; margin-top:4px;">'
            f"<b>Распознано:</b> {safe}</p>"
        )
    return f"<p>{safe}</p>"


def minute_changed(previous: str | None, current: str) -> bool:
    """Chat timestamps look like HH:MM; show one only when the minute changes."""
    return previous is None or previous != current

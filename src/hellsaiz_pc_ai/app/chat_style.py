"""Chat bubble rendering for the transcript QTextEdit.

Pure data: no Qt imports here so tests can run without a QApplication.
"""

from __future__ import annotations

import html

ASSISTANT_NAME = "Hellsaiz"


def _escape(text: str) -> str:
    return html.escape(str(text), quote=False)


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
            '<div style="border-left:3px solid #6d5df6; background:rgba(12,16,25,140);'
            ' padding:8px 12px; border-radius:10px; margin-top:6px;">'
            f'<span style="color:#9966ff;"><b>{ASSISTANT_NAME}:</b></span> {safe}</div>'
        )
    if role == "user":
        return (
            '<div style="background:rgba(215,228,245,22); border:1px solid rgba(215,228,245,60);'
            ' padding:8px 12px; border-radius:10px; margin-top:6px;">'
            '<span style="color:#8e98a6;"><b>Вы:</b></span> ' f"{safe}</div>"
        )
    if role == "recognized":
        return (
            '<p style="color:#8a93a1; font-size:11px; margin-top:4px;">'
            f"<b>Распознано:</b> {safe}</p>"
        )
    return f"<p>{safe}</p>"

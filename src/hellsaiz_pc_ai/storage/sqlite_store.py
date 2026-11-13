from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class ChatStore:
    """Local text history; audio and API secrets are deliberately excluded."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def add_message(self, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("Unsupported role")
        with self._connect() as db:
            db.execute(
                "INSERT INTO messages(created_at, role, content) VALUES (?, ?, ?)",
                (datetime.now(UTC).isoformat(), role, content),
            )

    def recent_messages(self, limit: int = 30) -> list[dict[str, str]]:
        limit = max(1, min(limit, 200))
        with self._connect() as db:
            rows = db.execute(
                "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def clear(self) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM messages")

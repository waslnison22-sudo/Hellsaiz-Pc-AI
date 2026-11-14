from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


MIN_DELAY_SECONDS = 10
MAX_DELAY_SECONDS = 30 * 24 * 60 * 60
MAX_MESSAGE_LENGTH = 300


@dataclass(frozen=True)
class Reminder:
    id: int
    message: str
    due_at: datetime


class ReminderStore:
    """Persistent one-shot reminders sharing the local SQLite database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'notified', 'dismissed'))
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_reminders_due "
                "ON reminders(status, due_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=5000")
        return db

    @staticmethod
    def _utc(value: datetime | None = None) -> datetime:
        current = value or datetime.now(UTC)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Reminder time must be timezone-aware.")
        return current.astimezone(UTC)

    def add(
        self,
        message: str,
        delay_seconds: int,
        now: datetime | None = None,
    ) -> Reminder:
        if not isinstance(message, str):
            raise TypeError("Reminder message must be text.")
        message = message.strip()
        if not message or len(message) > MAX_MESSAGE_LENGTH:
            raise ValueError(
                f"Reminder message must contain 1..{MAX_MESSAGE_LENGTH} characters."
            )
        if (
            isinstance(delay_seconds, bool)
            or not isinstance(delay_seconds, int)
            or not MIN_DELAY_SECONDS <= delay_seconds <= MAX_DELAY_SECONDS
        ):
            raise ValueError(
                f"Reminder delay must be {MIN_DELAY_SECONDS} seconds..30 days."
            )

        created_at = self._utc(now)
        due_at = created_at + timedelta(seconds=delay_seconds)
        with self._connect() as db:
            cursor = db.execute(
                """
                INSERT INTO reminders(message, due_at, created_at, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (message, due_at.isoformat(), created_at.isoformat()),
            )
            reminder_id = int(cursor.lastrowid)
        return Reminder(reminder_id, message, due_at)

    def list_pending(self) -> list[Reminder]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT id, message, due_at
                FROM reminders
                WHERE status = 'pending'
                ORDER BY due_at ASC, id ASC
                LIMIT 500
                """
            ).fetchall()
        return [
            Reminder(int(reminder_id), message, datetime.fromisoformat(due_at))
            for reminder_id, message, due_at in rows
        ]

    def take_due(self, now: datetime | None = None) -> list[Reminder]:
        current = self._utc(now).isoformat()
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT id, message, due_at
                FROM reminders
                WHERE status = 'pending' AND due_at <= ?
                ORDER BY due_at ASC, id ASC
                LIMIT 100
                """,
                (current,),
            ).fetchall()
            if rows:
                db.executemany(
                    "UPDATE reminders SET status = 'notified' WHERE id = ? AND status = 'pending'",
                    [(int(row[0]),) for row in rows],
                )
        return [
            Reminder(int(reminder_id), message, datetime.fromisoformat(due_at))
            for reminder_id, message, due_at in rows
        ]

    def dismiss(self, reminder_id: int) -> bool:
        if isinstance(reminder_id, bool) or not isinstance(reminder_id, int) or reminder_id < 1:
            raise ValueError("Reminder id must be a positive integer.")
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE reminders SET status = 'dismissed' "
                "WHERE id = ? AND status = 'pending'",
                (reminder_id,),
            )
            return cursor.rowcount == 1

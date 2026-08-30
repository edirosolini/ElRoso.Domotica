"""Persistence for timers and alarms.

Scheduled things have to survive a restart of the container: an alarm that
disappears because the service was updated at midnight is worse than no alarm.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ONCE = "once"
DAILY = "daily"
REPEATS = (ONCE, DAILY)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id  INTEGER NOT NULL,
    fires_at TEXT    NOT NULL,
    message  TEXT    NOT NULL,
    repeat   TEXT    NOT NULL DEFAULT 'once'
);
CREATE INDEX IF NOT EXISTS jobs_by_time ON jobs (fires_at);
"""


@dataclass(frozen=True)
class Job:
    id: int
    chat_id: int
    when: datetime
    message: str
    repeat: str = ONCE

    @property
    def is_daily(self) -> bool:
        return self.repeat == DAILY


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        chat_id=row["chat_id"],
        when=datetime.fromisoformat(row["fires_at"]),
        message=row["message"],
        repeat=row["repeat"],
    )


class Store:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, chat_id: int, when: datetime, message: str, repeat: str = ONCE) -> Job:
        if repeat not in REPEATS:
            raise ValueError(f"repeat inválido: {repeat}")
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (chat_id, fires_at, message, repeat) VALUES (?, ?, ?, ?)",
                (chat_id, when.isoformat(), message, repeat),
            )
            return Job(id=cursor.lastrowid, chat_id=chat_id, when=when, message=message, repeat=repeat)

    def pending(self, chat_id: int | None = None) -> list[Job]:
        query = "SELECT * FROM jobs"
        params: tuple = ()
        if chat_id is not None:
            query += " WHERE chat_id = ?"
            params = (chat_id,)
        query += " ORDER BY fires_at ASC, id ASC"
        with self._connect() as conn:
            return [_row_to_job(row) for row in conn.execute(query, params)]

    def get(self, job_id: int) -> Job | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def remove(self, job_id: int) -> bool:
        with self._connect() as conn:
            return conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,)).rowcount > 0

    def reschedule(self, job_id: int, when: datetime) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET fires_at = ? WHERE id = ?", (when.isoformat(), job_id))

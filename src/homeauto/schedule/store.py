"""Persistence for timers and alarms.

Scheduled things have to survive a restart of the container: an alarm that
disappears because the service was updated at midnight is worse than no alarm.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

ONCE = "once"
DAILY = "daily"
WEEKLY = "weekly"
REPEATS = (ONCE, DAILY, WEEKLY)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id  INTEGER NOT NULL,
    fires_at TEXT    NOT NULL,
    message  TEXT    NOT NULL,
    repeat   TEXT    NOT NULL DEFAULT 'once',
    device   TEXT,
    days     TEXT
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
    device: str | None = None
    days: str | None = None

    @property
    def is_daily(self) -> bool:
        return self.repeat == DAILY

    @property
    def is_weekly(self) -> bool:
        return self.repeat == WEEKLY

    @property
    def weekdays(self) -> list[int]:
        """ISO weekday numbers of a weekly job; empty for everything else."""
        return [int(part) for part in (self.days or "").split(",") if part.strip()]

    @property
    def devices(self) -> list[str]:
        """The column holds a comma-separated list; one device is the common case."""
        return [part.strip() for part in (self.device or "").split(",") if part.strip()]


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        chat_id=row["chat_id"],
        when=datetime.fromisoformat(row["fires_at"]),
        message=row["message"],
        repeat=row["repeat"],
        device=row["device"],
        days=row["days"],
    )


class Store:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._add_missing_columns(conn)

    @staticmethod
    def _add_missing_columns(conn: sqlite3.Connection) -> None:
        """Databases created before a column existed are already out there."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        if "device" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN device TEXT")
        if "days" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN days TEXT")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def add(
        self,
        chat_id: int,
        when: datetime,
        message: str,
        repeat: str = ONCE,
        device: str | None = None,
        days: Iterable[int] | None = None,
    ) -> Job:
        if repeat not in REPEATS:
            raise ValueError(f"repeat inválido: {repeat}")
        stored_days = ",".join(str(day) for day in sorted(days)) if days else None
        # A weekly job with no days would never find a day to fire on.
        if repeat == WEEKLY and not stored_days:
            raise ValueError("una alarma semanal necesita días")
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (chat_id, fires_at, message, repeat, device, days)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, when.isoformat(), message, repeat, device, stored_days),
            )
            return Job(
                id=cursor.lastrowid,
                chat_id=chat_id,
                when=when,
                message=message,
                repeat=repeat,
                device=device,
                days=stored_days,
            )

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

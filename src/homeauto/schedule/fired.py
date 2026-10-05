"""La última alarma, timer o recordatorio que sonó en cada chat, para poder posponerla."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from homeauto.schedule.store import ALARM

SCHEMA = """
CREATE TABLE IF NOT EXISTS last_fired (
    chat_id  INTEGER PRIMARY KEY,
    message  TEXT    NOT NULL,
    device   TEXT,
    fired_at TEXT    NOT NULL,
    kind     TEXT    NOT NULL DEFAULT 'alarm',
    job_id   INTEGER
);
"""


@dataclass(frozen=True)
class Fired:
    message: str
    device: str | None
    at: datetime
    kind: str = ALARM
    job_id: int | None = None


class FiredStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(last_fired)")}
            if "kind" not in columns:
                conn.execute(f"ALTER TABLE last_fired ADD COLUMN kind TEXT NOT NULL DEFAULT '{ALARM}'")
            if "job_id" not in columns:
                conn.execute("ALTER TABLE last_fired ADD COLUMN job_id INTEGER")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(
        self,
        chat_id: int,
        message: str,
        device: str | None,
        at: datetime,
        kind: str = ALARM,
        job_id: int | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO last_fired (chat_id, message, device, fired_at, kind, job_id)"
                " VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET message = excluded.message, "
                "device = excluded.device, fired_at = excluded.fired_at, kind = excluded.kind, "
                "job_id = excluded.job_id",
                (chat_id, message, device, at.isoformat(), kind, job_id),
            )

    def last(self, chat_id: int) -> Fired | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT message, device, fired_at, kind, job_id FROM last_fired WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if row is None:
            return None
        return Fired(
            row["message"],
            row["device"],
            datetime.fromisoformat(row["fired_at"]),
            row["kind"],
            row["job_id"],
        )

    def forget(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM last_fired WHERE chat_id = ?", (chat_id,))

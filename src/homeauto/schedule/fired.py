"""La última alarma o timer que sonó en cada chat, para poder posponerla."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS last_fired (
    chat_id  INTEGER PRIMARY KEY,
    message  TEXT    NOT NULL,
    device   TEXT,
    fired_at TEXT    NOT NULL
);
"""


@dataclass(frozen=True)
class Fired:
    message: str
    device: str | None
    at: datetime


class FiredStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(self, chat_id: int, message: str, device: str | None, at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO last_fired (chat_id, message, device, fired_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET message = excluded.message, "
                "device = excluded.device, fired_at = excluded.fired_at",
                (chat_id, message, device, at.isoformat()),
            )

    def last(self, chat_id: int) -> Fired | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT message, device, fired_at FROM last_fired WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        if row is None:
            return None
        return Fired(row["message"], row["device"], datetime.fromisoformat(row["fired_at"]))

    def forget(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM last_fired WHERE chat_id = ?", (chat_id,))

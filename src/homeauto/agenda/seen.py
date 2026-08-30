"""What was already announced.

Without this, every restart would shout the next hour's events again.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS announced (
    key        TEXT PRIMARY KEY,
    at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS announced_by_time ON announced (at);
"""


class SeenStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def was_seen(self, key: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM announced WHERE key = ?", (key,)).fetchone() is not None

    def mark(self, key: str, moment: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO announced (key, at) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
                (key, moment.isoformat()),
            )

    def forget_before(self, cutoff: datetime) -> None:
        """Keep the table from growing forever; a past event never repeats."""
        with self._connect() as conn:
            conn.execute("DELETE FROM announced WHERE at < ?", (cutoff.isoformat(),))

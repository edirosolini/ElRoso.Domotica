"""Small timestamps the watchers need to remember between runs."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS marks (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Marks:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, key: str) -> datetime | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM marks WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        try:
            return datetime.fromisoformat(row["value"])
        except ValueError:
            return None

    def set(self, key: str, moment: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO marks (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, moment.isoformat()),
            )

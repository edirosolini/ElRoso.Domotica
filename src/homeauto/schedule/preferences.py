"""Per-chat choices that outlive a restart. Shares the file with the jobs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS preferences (
    chat_id        INTEGER PRIMARY KEY,
    default_device TEXT
);
"""


class Preferences:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def default_device(self, chat_id: int) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT default_device FROM preferences WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return row["default_device"] if row else None

    def set_default_device(self, chat_id: int, alias: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO preferences (chat_id, default_device) VALUES (?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET default_device = excluded.default_device",
                (chat_id, alias.strip().lower()),
            )

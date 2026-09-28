"""Los recordatorios que sonaron y nadie marcó como hechos todavía."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Pasado esto, un «Hecho» ya no encuentra nada que cerrar.
KEEP = timedelta(days=1)

SCHEMA = """
CREATE TABLE IF NOT EXISTS awaiting_done (
    job_id   INTEGER PRIMARY KEY,
    message  TEXT    NOT NULL,
    fired_at TEXT    NOT NULL
);
"""


class AwaitingStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(self, job_id: int, message: str, at: datetime) -> None:
        """Deja el job esperando su «Hecho» y borra lo que venció."""
        with self._connect() as conn:
            conn.execute("DELETE FROM awaiting_done WHERE fired_at < ?", ((at - KEEP).isoformat(),))
            conn.execute(
                "INSERT INTO awaiting_done (job_id, message, fired_at) VALUES (?, ?, ?) "
                "ON CONFLICT(job_id) DO UPDATE SET message = excluded.message, "
                "fired_at = excluded.fired_at",
                (job_id, message, at.isoformat()),
            )

    def take(self, job_id: int) -> str | None:
        """El mensaje del job, sacándolo de la espera; None si ya no esperaba."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT message FROM awaiting_done WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return None
            deleted = conn.execute("DELETE FROM awaiting_done WHERE job_id = ?", (job_id,))
        # Dos toques a la vez: solo el que borró la fila lo marca.
        return row["message"] if deleted.rowcount else None

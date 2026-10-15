"""Las alarmas que están sonando y nadie apagó todavía."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS ringing (
    job_id    INTEGER PRIMARY KEY,
    chat_id   INTEGER,
    message   TEXT    NOT NULL,
    devices   TEXT,
    fired_at  TEXT    NOT NULL,
    rings     INTEGER NOT NULL DEFAULT 0,
    next_ring TEXT
);
"""


@dataclass(frozen=True)
class Ringing:
    job_id: int
    chat_id: int | None
    message: str
    devices: str | None
    fired_at: datetime
    rings: int = 0
    next_ring: datetime | None = None


def _row_to_ringing(row: sqlite3.Row) -> Ringing:
    return Ringing(
        job_id=row["job_id"],
        chat_id=row["chat_id"],
        message=row["message"],
        devices=row["devices"],
        fired_at=datetime.fromisoformat(row["fired_at"]),
        rings=row["rings"],
        next_ring=datetime.fromisoformat(row["next_ring"]) if row["next_ring"] else None,
    )


class RingingStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._add_missing_columns(conn)

    @staticmethod
    def _add_missing_columns(conn: sqlite3.Connection) -> None:
        """Agrega las columnas que la tabla no tenga."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(ringing)")}
        if "devices" not in existing:
            conn.execute("ALTER TABLE ringing ADD COLUMN devices TEXT")
        if "rings" not in existing:
            conn.execute("ALTER TABLE ringing ADD COLUMN rings INTEGER NOT NULL DEFAULT 0")
        if "next_ring" not in existing:
            conn.execute("ALTER TABLE ringing ADD COLUMN next_ring TEXT")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(
        self, job_id: int, chat_id: int | None, message: str, devices: str | None, at: datetime
    ) -> None:
        """Deja la alarma sonando desde `at`, sin repeticiones todavía."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO ringing (job_id, chat_id, message, devices, fired_at, rings, next_ring)"
                " VALUES (?, ?, ?, ?, ?, 0, NULL) "
                "ON CONFLICT(job_id) DO UPDATE SET chat_id = excluded.chat_id, "
                "message = excluded.message, devices = excluded.devices, "
                "fired_at = excluded.fired_at, rings = 0, next_ring = NULL",
                (job_id, chat_id, message, devices, at.isoformat()),
            )

    def get(self, job_id: int) -> Ringing | None:
        """La alarma que suena, o None si ya no suena."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ringing WHERE job_id = ?", (job_id,)).fetchone()
        return _row_to_ringing(row) if row else None

    def all(self) -> list[Ringing]:
        """Todas las que suenan."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM ringing ORDER BY job_id").fetchall()
        return [_row_to_ringing(row) for row in rows]

    def mark_rang(self, job_id: int) -> None:
        """Suma una repetición."""
        with self._connect() as conn:
            conn.execute("UPDATE ringing SET rings = rings + 1 WHERE job_id = ?", (job_id,))

    def set_next(self, job_id: int, when: datetime) -> bool:
        """Fija la próxima repetición; False si ya no suena."""
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE ringing SET next_ring = ? WHERE job_id = ?", (when.isoformat(), job_id)
            )
        return changed.rowcount > 0

    def take(self, job_id: int) -> Ringing | None:
        """La alarma, dejándola de sonar; None si ya no sonaba."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ringing WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            deleted = conn.execute("DELETE FROM ringing WHERE job_id = ?", (job_id,))
        # Dos toques a la vez: solo el que borró la fila la apaga.
        return _row_to_ringing(row) if deleted.rowcount else None

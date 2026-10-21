"""Los recordatorios que sonaron y nadie marcó como hechos todavía."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from homeauto.schedule.store import NOBODY, pack_chats, unpack_chats

# Pasado esto, un «Hecho» ya no encuentra nada que cerrar.
KEEP = timedelta(days=1)

SCHEMA = """
CREATE TABLE IF NOT EXISTS awaiting_done (
    job_id   INTEGER PRIMARY KEY,
    message  TEXT    NOT NULL,
    fired_at TEXT    NOT NULL,
    nags     INTEGER NOT NULL DEFAULT 0,
    next_nag TEXT,
    stock_id INTEGER,
    assignee TEXT    NOT NULL DEFAULT 'none',
    assignee_id INTEGER,
    audience TEXT,
    devices  TEXT
);
"""


@dataclass(frozen=True)
class Waiting:
    job_id: int
    message: str
    fired_at: datetime
    nags: int = 0
    next_nag: datetime | None = None
    stock_id: int | None = None
    # Para quién era y a qué chats llegó; `audience` None es todos.
    assignee: str = NOBODY
    assignee_id: int | None = None
    audience: tuple[int, ...] | None = None
    # Los equipos en que sonó, separados por coma; None es el de siempre.
    devices: str | None = None


def _row_to_waiting(row: sqlite3.Row) -> Waiting:
    return Waiting(
        job_id=row["job_id"],
        message=row["message"],
        fired_at=datetime.fromisoformat(row["fired_at"]),
        nags=row["nags"],
        next_nag=datetime.fromisoformat(row["next_nag"]) if row["next_nag"] else None,
        stock_id=row["stock_id"],
        assignee=row["assignee"],
        assignee_id=row["assignee_id"],
        audience=unpack_chats(row["audience"]),
        devices=row["devices"],
    )


class AwaitingStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._add_missing_columns(conn)

    @staticmethod
    def _add_missing_columns(conn: sqlite3.Connection) -> None:
        """Agrega las columnas del re-aviso, del stock, de la asignación y de los equipos si faltan."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(awaiting_done)")}
        if "nags" not in existing:
            conn.execute("ALTER TABLE awaiting_done ADD COLUMN nags INTEGER NOT NULL DEFAULT 0")
        if "next_nag" not in existing:
            conn.execute("ALTER TABLE awaiting_done ADD COLUMN next_nag TEXT")
        if "stock_id" not in existing:
            conn.execute("ALTER TABLE awaiting_done ADD COLUMN stock_id INTEGER")
        if "assignee" not in existing:
            conn.execute(
                f"ALTER TABLE awaiting_done ADD COLUMN assignee TEXT NOT NULL DEFAULT '{NOBODY}'"
            )
        if "assignee_id" not in existing:
            conn.execute("ALTER TABLE awaiting_done ADD COLUMN assignee_id INTEGER")
        if "audience" not in existing:
            conn.execute("ALTER TABLE awaiting_done ADD COLUMN audience TEXT")
        if "devices" not in existing:
            conn.execute("ALTER TABLE awaiting_done ADD COLUMN devices TEXT")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(
        self,
        job_id: int,
        message: str,
        at: datetime,
        next_nag: datetime | None = None,
        stock_id: int | None = None,
        assignee: str = NOBODY,
        assignee_id: int | None = None,
        audience: tuple[int, ...] | None = None,
        devices: str | None = None,
    ) -> None:
        """Deja el job esperando su «Hecho» y borra lo que venció."""
        with self._connect() as conn:
            conn.execute("DELETE FROM awaiting_done WHERE fired_at < ?", ((at - KEEP).isoformat(),))
            conn.execute(
                "INSERT INTO awaiting_done (job_id, message, fired_at, nags, next_nag, stock_id,"
                " assignee, assignee_id, audience, devices) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(job_id) DO UPDATE SET message = excluded.message, "
                "fired_at = excluded.fired_at, nags = 0, next_nag = excluded.next_nag, "
                "stock_id = excluded.stock_id, assignee = excluded.assignee, "
                "assignee_id = excluded.assignee_id, audience = excluded.audience, "
                "devices = excluded.devices",
                (job_id, message, at.isoformat(), next_nag.isoformat() if next_nag else None,
                 stock_id, assignee, assignee_id, pack_chats(audience), devices),
            )

    def get(self, job_id: int) -> Waiting | None:
        """Lo que espera el job, o None si ya no espera."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM awaiting_done WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _row_to_waiting(row) if row else None

    def all(self) -> list[Waiting]:
        """Todo lo que espera su «Hecho», de lo que sonó antes a lo último."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM awaiting_done ORDER BY fired_at, job_id").fetchall()
        return [_row_to_waiting(row) for row in rows]

    def mark_nagged(self, job_id: int, next_nag: datetime | None) -> None:
        """Suma un re-aviso y fija el próximo; None no re-avisa más."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE awaiting_done SET nags = nags + 1, next_nag = ? WHERE job_id = ?",
                (next_nag.isoformat() if next_nag else None, job_id),
            )

    def stop_nagging(self, job_id: int) -> None:
        """Deja de re-avisar sin sacar el job de la espera."""
        with self._connect() as conn:
            conn.execute("UPDATE awaiting_done SET next_nag = NULL WHERE job_id = ?", (job_id,))

    def due_nags(self) -> list[Waiting]:
        """Los que todavía tienen un re-aviso por delante."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM awaiting_done WHERE next_nag IS NOT NULL ORDER BY next_nag"
            ).fetchall()
        return [_row_to_waiting(row) for row in rows]

    def drop_before(self, job_id: int, cutoff: datetime) -> bool:
        """Saca el job de la espera solo si sonó antes de `cutoff`; True si lo sacó."""
        with self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM awaiting_done WHERE job_id = ? AND fired_at < ?",
                (job_id, cutoff.isoformat()),
            )
        return deleted.rowcount > 0

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

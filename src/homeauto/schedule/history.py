"""El historial de todo lo que sonó y cómo terminó cada aviso."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from homeauto.schedule.store import NOBODY, pack_chats, unpack_chats

# Lo que sonó hace más que esto se borra al registrar un aviso nuevo.
KEEP = timedelta(days=365)

DONE = "done"
SNOOZE = "snooze"
CANCEL = "cancel"
OFF = "off"
HOLIDAY = "holiday"

SCHEMA = """
CREATE TABLE IF NOT EXISTS fired_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER,
    chat_id    INTEGER,
    kind       TEXT    NOT NULL,
    repeat     TEXT    NOT NULL DEFAULT 'once',
    message    TEXT    NOT NULL,
    fired_at   TEXT    NOT NULL,
    announced  INTEGER NOT NULL DEFAULT 0,
    done_at    TEXT,
    done_by    TEXT,
    nags       INTEGER NOT NULL DEFAULT 0,
    snoozed_at TEXT,
    closed     TEXT,
    closed_at  TEXT,
    assignee   TEXT    NOT NULL DEFAULT 'none',
    assignee_id INTEGER,
    audience   TEXT
);
CREATE INDEX IF NOT EXISTS fired_history_fired_at ON fired_history (fired_at);
"""

# La última fila sin cerrar del job.
_LAST_OPEN = (
    "id = (SELECT id FROM fired_history WHERE job_id = ? AND closed IS NULL"
    " ORDER BY id DESC LIMIT 1)"
)


@dataclass(frozen=True)
class Entry:
    id: int
    job_id: int | None
    chat_id: int | None
    kind: str
    repeat: str
    message: str
    fired_at: datetime
    announced: bool
    done_at: datetime | None
    done_by: str | None
    nags: int
    snoozed_at: datetime | None
    closed: str | None
    closed_at: datetime | None = None
    # Para quién era y a qué chats llegó; `audience` None es todos.
    assignee: str = NOBODY
    assignee_id: int | None = None
    audience: tuple[int, ...] | None = None


def _when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _row_to_entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=row["id"],
        job_id=row["job_id"],
        chat_id=row["chat_id"],
        kind=row["kind"],
        repeat=row["repeat"],
        message=row["message"],
        fired_at=datetime.fromisoformat(row["fired_at"]),
        announced=bool(row["announced"]),
        done_at=_when(row["done_at"]),
        done_by=row["done_by"],
        nags=row["nags"],
        snoozed_at=_when(row["snoozed_at"]),
        closed=row["closed"],
        closed_at=_when(row["closed_at"]),
        assignee=row["assignee"],
        assignee_id=row["assignee_id"],
        audience=unpack_chats(row["audience"]),
    )


class HistoryStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._add_missing_columns(conn)

    @staticmethod
    def _add_missing_columns(conn: sqlite3.Connection) -> None:
        """Agrega las columnas de la asignación si la tabla no las tiene."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(fired_history)")}
        if "assignee" not in existing:
            conn.execute(
                f"ALTER TABLE fired_history ADD COLUMN assignee TEXT NOT NULL DEFAULT '{NOBODY}'"
            )
        if "assignee_id" not in existing:
            conn.execute("ALTER TABLE fired_history ADD COLUMN assignee_id INTEGER")
        if "audience" not in existing:
            conn.execute("ALTER TABLE fired_history ADD COLUMN audience TEXT")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def record(
        self,
        job_id: int,
        chat_id: int | None,
        kind: str,
        repeat: str,
        message: str,
        at: datetime,
        assignee: str = NOBODY,
        assignee_id: int | None = None,
        audience: tuple[int, ...] | None = None,
    ) -> None:
        """Abre la fila de un aviso que sonó, todavía sin dar por dicho, y poda lo vencido."""
        with self._connect() as conn:
            conn.execute("DELETE FROM fired_history WHERE fired_at < ?", ((at - KEEP).isoformat(),))
            conn.execute(
                "INSERT INTO fired_history (job_id, chat_id, kind, repeat, message, fired_at,"
                " assignee, assignee_id, audience) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (job_id, chat_id, kind, repeat, message, at.isoformat(), assignee, assignee_id,
                 pack_chats(audience)),
            )

    def mark_announced(self, job_id: int) -> None:
        """Da por dicho el último aviso abierto del job."""
        self._update(job_id, "announced = 1")

    def mark_nag(self, job_id: int) -> None:
        """Suma un re-aviso al último aviso abierto del job."""
        self._update(job_id, "nags = nags + 1")

    def mark_done(self, job_id: int, at: datetime, who: str) -> bool:
        """Cierra como hecho el último aviso abierto del job; False si no había."""
        return self._update(
            job_id,
            "done_at = ?, done_by = ?, closed = ?, closed_at = ?",
            (at.isoformat(), who, DONE, at.isoformat()),
        )

    def mark_off(self, job_id: int, at: datetime, who: str) -> bool:
        """Cierra como apagada la última alarma abierta del job; False si no había."""
        return self._update(
            job_id,
            "done_by = ?, closed = ?, closed_at = ?",
            (who, OFF, at.isoformat()),
        )

    def mark_closed(self, job_id: int, how: str, at: datetime) -> bool:
        """Cierra el último aviso abierto del job como pospuesto, cancelado o feriado; False si no había."""
        if how == SNOOZE:
            return self._update(
                job_id,
                "snoozed_at = ?, closed = ?, closed_at = ?",
                (at.isoformat(), SNOOZE, at.isoformat()),
            )
        if how in (CANCEL, HOLIDAY):
            return self._update(job_id, "closed = ?, closed_at = ?", (how, at.isoformat()))
        raise ValueError(f"unknown way of closing: {how}")

    def between(self, start: datetime, end: datetime) -> list[Entry]:
        """Los avisos que sonaron desde `start` hasta antes de `end`, en orden."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fired_history WHERE fired_at >= ? AND fired_at < ?"
                " ORDER BY fired_at, id",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return [_row_to_entry(row) for row in rows]

    def latest(self, job_id: int, count: int) -> list[Entry]:
        """Las últimas `count` filas del job, de la más nueva a la más vieja, sin las de feriado."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fired_history WHERE job_id = ? AND (closed IS NULL OR closed != ?)"
                " ORDER BY fired_at DESC, id DESC LIMIT ?",
                (job_id, HOLIDAY, count),
            ).fetchall()
        return [_row_to_entry(row) for row in rows]

    def count_before(self, before: datetime) -> int:
        """Cuántas filas cerradas sonaron antes de `before`."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM fired_history WHERE closed IS NOT NULL AND fired_at < ?",
                (before.isoformat(),),
            ).fetchone()
        return row[0]

    def delete_before(self, before: datetime, closed_by: datetime) -> int:
        """Borra las filas que sonaron antes de `before` y ya estaban cerradas en `closed_by`."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM fired_history WHERE closed IS NOT NULL AND fired_at < ?"
                " AND (closed_at IS NULL OR closed_at <= ?)",
                (before.isoformat(), closed_by.isoformat()),
            )
        return cursor.rowcount

    def _update(self, job_id: int, assignments: str, values: tuple = ()) -> bool:
        with self._connect() as conn:
            changed = conn.execute(
                f"UPDATE fired_history SET {assignments} WHERE {_LAST_OPEN}", (*values, job_id)
            )
        return changed.rowcount > 0

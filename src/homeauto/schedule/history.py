"""El historial de todo lo que sonó y cómo terminó cada aviso."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

# Lo que sonó hace más que esto se borra al registrar un aviso nuevo.
KEEP = timedelta(days=365)

DONE = "done"
SNOOZE = "snooze"
CANCEL = "cancel"

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
    closed_at  TEXT
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
    )


class HistoryStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

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
    ) -> None:
        """Abre la fila de un aviso que sonó, todavía sin dar por dicho, y poda lo vencido."""
        with self._connect() as conn:
            conn.execute("DELETE FROM fired_history WHERE fired_at < ?", ((at - KEEP).isoformat(),))
            conn.execute(
                "INSERT INTO fired_history (job_id, chat_id, kind, repeat, message, fired_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, chat_id, kind, repeat, message, at.isoformat()),
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

    def mark_closed(self, job_id: int, how: str, at: datetime) -> bool:
        """Cierra el último aviso abierto del job como pospuesto o cancelado; False si no había."""
        if how == SNOOZE:
            return self._update(
                job_id,
                "snoozed_at = ?, closed = ?, closed_at = ?",
                (at.isoformat(), SNOOZE, at.isoformat()),
            )
        if how == CANCEL:
            return self._update(job_id, "closed = ?, closed_at = ?", (CANCEL, at.isoformat()))
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

    def _update(self, job_id: int, assignments: str, values: tuple = ()) -> bool:
        with self._connect() as conn:
            changed = conn.execute(
                f"UPDATE fired_history SET {assignments} WHERE {_LAST_OPEN}", (*values, job_id)
            )
        return changed.rowcount > 0

"""La última alarma, timer o recordatorio que sonó en cada chat, para poder posponerla."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from homeauto.schedule.store import ALARM, NOBODY, pack_chats, unpack_chats

SCHEMA = """
CREATE TABLE IF NOT EXISTS last_fired (
    chat_id  INTEGER PRIMARY KEY,
    message  TEXT    NOT NULL,
    device   TEXT,
    fired_at TEXT    NOT NULL,
    kind     TEXT    NOT NULL DEFAULT 'alarm',
    job_id   INTEGER,
    stock_id INTEGER,
    assignee TEXT    NOT NULL DEFAULT 'none',
    assignee_id INTEGER,
    audience TEXT
);
"""


@dataclass(frozen=True)
class Fired:
    message: str
    device: str | None
    at: datetime
    kind: str = ALARM
    job_id: int | None = None
    stock_id: int | None = None
    # Para quién era y a qué chats llegó; `audience` None es todos.
    assignee: str = NOBODY
    assignee_id: int | None = None
    audience: tuple[int, ...] | None = None


_COLUMNS = "message, device, fired_at, kind, job_id, stock_id, assignee, assignee_id, audience"


def _row_to_fired(row: sqlite3.Row) -> Fired:
    return Fired(
        row["message"],
        row["device"],
        datetime.fromisoformat(row["fired_at"]),
        row["kind"],
        row["job_id"],
        row["stock_id"],
        row["assignee"],
        row["assignee_id"],
        unpack_chats(row["audience"]),
    )


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
            if "stock_id" not in columns:
                conn.execute("ALTER TABLE last_fired ADD COLUMN stock_id INTEGER")
            if "assignee" not in columns:
                conn.execute(
                    f"ALTER TABLE last_fired ADD COLUMN assignee TEXT NOT NULL DEFAULT '{NOBODY}'"
                )
            if "assignee_id" not in columns:
                conn.execute("ALTER TABLE last_fired ADD COLUMN assignee_id INTEGER")
            if "audience" not in columns:
                conn.execute("ALTER TABLE last_fired ADD COLUMN audience TEXT")

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
        stock_id: int | None = None,
        assignee: str = NOBODY,
        assignee_id: int | None = None,
        audience: tuple[int, ...] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO last_fired (chat_id, {_COLUMNS})"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET message = excluded.message, "
                "device = excluded.device, fired_at = excluded.fired_at, kind = excluded.kind, "
                "job_id = excluded.job_id, stock_id = excluded.stock_id, "
                "assignee = excluded.assignee, assignee_id = excluded.assignee_id, "
                "audience = excluded.audience",
                (chat_id, message, device, at.isoformat(), kind, job_id, stock_id,
                 assignee, assignee_id, pack_chats(audience)),
            )

    def last(self, chat_id: int) -> Fired | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM last_fired WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return _row_to_fired(row) if row is not None else None

    def forget(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM last_fired WHERE chat_id = ?", (chat_id,))

    def all(self) -> list[tuple[int, Fired]]:
        """Cada chat con lo último que sonó en él, por número de chat."""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT chat_id, {_COLUMNS} FROM last_fired ORDER BY chat_id"
            ).fetchall()
        return [(row["chat_id"], _row_to_fired(row)) for row in rows]

    def forget_before(self, chat_id: int, cutoff: datetime) -> bool:
        """Olvida lo que sonó en el chat solo si sonó antes de `cutoff`; True si lo olvidó."""
        with self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM last_fired WHERE chat_id = ? AND fired_at < ?",
                (chat_id, cutoff.isoformat()),
            )
        return deleted.rowcount > 0

"""Recuerda qué ya se avisó, para que el monitor siga siendo soportable."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS service_status (
    name     TEXT PRIMARY KEY,
    up       INTEGER NOT NULL,
    failures INTEGER NOT NULL DEFAULT 0,
    alerted  INTEGER NOT NULL DEFAULT 0,
    detail   TEXT NOT NULL DEFAULT '',
    since    TEXT NOT NULL
);
"""


# La confirmación y los re-avisos de una caída: `save()` no las toca.
ALERT_COLUMNS = (
    ("acked_by", "TEXT"),
    ("acked_at", "TEXT"),
    ("reminders", "INTEGER NOT NULL DEFAULT 0"),
    ("next_reminder", "TEXT"),
)


@dataclass(frozen=True)
class Status:
    name: str
    up: bool
    failures: int
    alerted: bool
    detail: str
    since: datetime
    acked_by: str = ""
    acked_at: datetime | None = None
    reminders: int = 0
    next_reminder: datetime | None = None


class StatusStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._add_missing_columns(conn)

    @staticmethod
    def _add_missing_columns(conn: sqlite3.Connection) -> None:
        """Agrega las columnas de la confirmación y los re-avisos si la tabla no las tiene."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(service_status)")}
        for column, kind in ALERT_COLUMNS:
            if column not in existing:
                conn.execute(f"ALTER TABLE service_status ADD COLUMN {column} {kind}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, name: str) -> Status | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM service_status WHERE name = ?", (name,)).fetchone()
        return self._to_status(row) if row else None

    def all(self) -> dict[str, Status]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM service_status ORDER BY name").fetchall()
        return {row["name"]: self._to_status(row) for row in rows}

    def save(self, status: Status) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO service_status (name, up, failures, alerted, detail, since) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET up=excluded.up, failures=excluded.failures, "
                "alerted=excluded.alerted, detail=excluded.detail, since=excluded.since",
                (
                    status.name,
                    int(status.up),
                    status.failures,
                    int(status.alerted),
                    status.detail,
                    status.since.isoformat(),
                ),
            )

    def acknowledge(self, name: str, who: str, at: datetime) -> bool:
        """Marca confirmada una caída avisada y sin confirmar; False si no había cuál."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE service_status SET acked_by = ?, acked_at = ? "
                "WHERE name = ? AND up = 0 AND alerted = 1 AND acked_by IS NULL",
                (who, at.isoformat(), name),
            )
        return cursor.rowcount == 1

    def plan_reminder(self, name: str, reminders: int, at: datetime) -> None:
        """Guarda cuántos re-avisos salieron y cuándo toca el próximo."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE service_status SET reminders = ?, next_reminder = ? WHERE name = ?",
                (reminders, at.isoformat(), name),
            )

    def clear_alert(self, name: str) -> None:
        """Olvida la confirmación y los re-avisos de la caída."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE service_status SET acked_by = NULL, acked_at = NULL, reminders = 0, "
                "next_reminder = NULL WHERE name = ?",
                (name,),
            )

    @staticmethod
    def _to_status(row: sqlite3.Row) -> Status:
        return Status(
            name=row["name"],
            up=bool(row["up"]),
            failures=row["failures"],
            alerted=bool(row["alerted"]),
            detail=row["detail"],
            since=datetime.fromisoformat(row["since"]),
            acked_by=row["acked_by"] or "",
            acked_at=_moment(row["acked_at"]),
            reminders=row["reminders"],
            next_reminder=_moment(row["next_reminder"]),
        )


def _moment(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None

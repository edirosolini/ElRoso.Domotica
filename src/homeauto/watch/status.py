"""Remembering what was already reported, so the monitor stays bearable."""

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


@dataclass(frozen=True)
class Status:
    name: str
    up: bool
    failures: int
    alerted: bool
    detail: str
    since: datetime


class StatusStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

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

    @staticmethod
    def _to_status(row: sqlite3.Row) -> Status:
        return Status(
            name=row["name"],
            up=bool(row["up"]),
            failures=row["failures"],
            alerted=bool(row["alerted"]),
            detail=row["detail"],
            since=datetime.fromisoformat(row["since"]),
        )

"""Las teles con la app de la casa: quién se registró, con qué versión y si sigue viva."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

# Lo que una tele puede saber hacer; lo demás se ignora.
CAPS = ("play", "show", "overlay")
# Sin latido en este tiempo, la tele se da por muerta.
STALE = timedelta(minutes=3)
# Cada cuánto, como mucho, un latido se anota en disco.
WRITE_EVERY = timedelta(minutes=1)

SCHEMA = """
CREATE TABLE IF NOT EXISTS teles (
    alias        TEXT PRIMARY KEY,
    version_name TEXT    NOT NULL DEFAULT '',
    version_code INTEGER NOT NULL DEFAULT 0,
    caps         TEXT    NOT NULL DEFAULT '',
    last_seen    TEXT,
    address      TEXT    NOT NULL DEFAULT ''
);
"""

# Las columnas que una tabla vieja puede no tener, con su definición.
COLUMNS = {
    "version_name": "TEXT NOT NULL DEFAULT ''",
    "version_code": "INTEGER NOT NULL DEFAULT 0",
    "caps": "TEXT NOT NULL DEFAULT ''",
    "last_seen": "TEXT",
    "address": "TEXT NOT NULL DEFAULT ''",
}


def normalize(alias: str) -> str:
    return alias.strip().lower()


@dataclass(frozen=True)
class Tele:
    alias: str
    version_name: str
    version_code: int
    caps: tuple[str, ...]
    last_seen: datetime | None
    address: str


def _row_to_tele(row: sqlite3.Row) -> Tele:
    return Tele(
        alias=row["alias"],
        version_name=row["version_name"],
        version_code=row["version_code"],
        caps=tuple(cap for cap in row["caps"].split(",") if cap),
        last_seen=datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else None,
        address=row["address"],
    )


class TeleStore:
    """Una fila por tele registrada, dueña de su esquema."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._add_missing_columns(conn)

    @staticmethod
    def _add_missing_columns(conn: sqlite3.Connection) -> None:
        """Agrega las columnas que la tabla no tiene."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(teles)")}
        for name, definition in COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE teles ADD COLUMN {name} {definition}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, tele: Tele) -> None:
        """Guarda la tele, pisando lo que había de ella."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO teles (alias, version_name, version_code, caps, last_seen, address)"
                " VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(alias) DO UPDATE SET version_name = excluded.version_name, "
                "version_code = excluded.version_code, caps = excluded.caps, "
                "last_seen = excluded.last_seen, address = excluded.address",
                (
                    tele.alias,
                    tele.version_name,
                    tele.version_code,
                    ",".join(tele.caps),
                    tele.last_seen.isoformat() if tele.last_seen else None,
                    tele.address,
                ),
            )

    def seen(self, alias: str, at: datetime, address: str) -> None:
        """Anota el último latido de la tele y desde qué dirección llegó."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE teles SET last_seen = ?, address = ? WHERE alias = ?",
                (at.isoformat(), address, alias),
            )

    def get(self, alias: str) -> Tele | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM teles WHERE alias = ?", (alias,)).fetchone()
        return _row_to_tele(row) if row else None

    def all(self) -> list[Tele]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM teles ORDER BY alias").fetchall()
        return [_row_to_tele(row) for row in rows]


class TeleLink:
    """El registro y el latido de cada tele; el latido va a disco como mucho una vez por minuto."""

    def __init__(self, store: TeleStore, clock: Callable[[], datetime] = datetime.now):
        self.store = store
        self.clock = clock
        # El último latido de cada tele y cuándo se anotó en disco.
        self._beats: dict[str, datetime] = {}
        self._written: dict[str, datetime] = {}

    def hello(
        self,
        alias: str,
        version_name: str,
        version_code: int,
        caps: Iterable[str],
        address: str,
    ) -> Tele:
        """Registra la tele, o la actualiza, y cuenta como latido."""
        now = self.clock()
        tele = Tele(normalize(alias), version_name, version_code, tuple(caps), now, address)
        self.store.save(tele)
        self._beats[tele.alias] = now
        self._written[tele.alias] = now
        return tele

    def beat(self, alias: str, address: str) -> bool:
        """Anota un latido; False si la tele nunca se registró."""
        alias = normalize(alias)
        if not self._known(alias):
            return False
        now = self.clock()
        self._beats[alias] = now
        written = self._written.get(alias)
        if written is None or now - written >= WRITE_EVERY:
            self.store.seen(alias, now, address)
            self._written[alias] = now
        return True

    def alive(self, alias: str) -> bool:
        """Si la tele latió hace menos de `STALE`."""
        alias = normalize(alias)
        if not self._known(alias):
            return False
        last = self._beats.get(alias)
        return last is not None and self.clock() - last < STALE

    def _known(self, alias: str) -> bool:
        """Si la tele está registrada; la primera vez trae de disco su último latido."""
        if alias in self._beats:
            return True
        tele = self.store.get(alias)
        if tele is None:
            return False
        if tele.last_seen is not None:
            self._beats[alias] = tele.last_seen
            self._written[alias] = tele.last_seen
        return True

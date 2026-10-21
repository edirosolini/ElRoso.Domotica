"""Las teles con la app de la casa: quién se registró, con qué versión y si sigue viva."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

# Lo que una tele puede saber hacer; lo demás se ignora.
CAPS = ("play", "show", "overlay")
# Lo que la app puede contestar de una orden.
ACK_STATES = ("received", "done", "failed")
# Estados de una orden que ya no cambian.
CLOSED = ("done", "failed", "cancelled")
# Órdenes que terminan al llegar a la app.
DELIVERED_ONLY = ("show", "stop")
# Cuántas órdenes cerradas se guardan por tele.
KEEP_CLOSED = 32
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


@dataclass
class _Order:
    seq: int
    fields: dict
    state: str = "pending"


class TeleLink:
    """El registro, el latido y el buzón de órdenes de cada tele."""

    def __init__(self, store: TeleStore, clock: Callable[[], datetime] = datetime.now):
        self.store = store
        self.clock = clock
        # El último latido de cada tele y cuándo se anotó en disco.
        self._beats: dict[str, datetime] = {}
        self._written: dict[str, datetime] = {}
        self._caps: dict[str, tuple[str, ...]] = {}
        # Las órdenes de cada tele, por seq; el seq arranca en el milisegundo del arranque.
        self._orders: dict[str, dict[int, _Order]] = {}
        self._first_seq = int(clock().timestamp() * 1000)
        self._last_seq: dict[str, int] = {}
        self._changed = threading.Condition()

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
        self._caps[tele.alias] = tele.caps
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

    def can(self, alias: str, cap: str) -> bool:
        """Si la tele está viva y anunció esa capacidad."""
        alias = normalize(alias)
        return self.alive(alias) and cap in self._caps.get(alias, ())

    def send(self, alias: str, kind: str, **fields) -> int:
        """Deja una orden en el buzón y devuelve su seq; `stop` anula las que siguen abiertas."""
        alias = normalize(alias)
        with self._changed:
            orders = self._orders.setdefault(alias, {})
            closed = [seq for seq, order in orders.items() if order.state in CLOSED]
            for seq in closed[:-KEEP_CLOSED]:
                del orders[seq]
            if kind == "stop":
                for order in orders.values():
                    order.state = "cancelled"
                self._changed.notify_all()
            seq = max(self._last_seq.get(alias, self._first_seq), self._first_seq) + 1
            self._last_seq[alias] = seq
            orders[seq] = _Order(seq, {"kind": kind, **fields})
            return seq

    def orders(self, alias: str) -> list[dict]:
        """Las órdenes que la app todavía no confirmó haber recibido."""
        alias = normalize(alias)
        with self._changed:
            pending = [o for o in self._orders.get(alias, {}).values() if o.state == "pending"]
            return [{"seq": order.seq, **order.fields} for order in pending]

    def ack(self, alias: str, seq: int, state: str) -> bool | None:
        """Anota lo que la app dice de una orden; False si no existe o ya cerró, None si la tele no."""
        alias = normalize(alias)
        if not self._known(alias):
            return None
        with self._changed:
            order = self._orders.get(alias, {}).get(seq)
            if order is None or order.state in CLOSED:
                return False
            if state == "received" and order.state == "received":
                return True
            if state == "received" and order.fields["kind"] in DELIVERED_ONLY:
                state = "done"
            order.state = state
            self._changed.notify_all()
            return True

    def cancel(self, alias: str, seq: int) -> None:
        """Anula una orden abierta; un ack que llegue después se ignora."""
        alias = normalize(alias)
        with self._changed:
            order = self._orders.get(alias, {}).get(seq)
            if order is not None and order.state not in CLOSED:
                order.state = "cancelled"
                self._changed.notify_all()

    def wait(self, alias: str, seq: int, states: Iterable[str], timeout: float) -> str | None:
        """Espera a que la orden llegue a uno de `states` o cierre; None si se acaba el tiempo."""
        alias = normalize(alias)
        wanted = set(states) | set(CLOSED)
        deadline = time.monotonic() + timeout
        with self._changed:
            while True:
                order = self._orders.get(alias, {}).get(seq)
                if order is None:
                    return "cancelled"
                if order.state in wanted:
                    return order.state
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self._changed.wait(left)

    def _known(self, alias: str) -> bool:
        """Si la tele está registrada; la primera vez trae de disco su último latido."""
        if alias in self._beats or alias in self._caps:
            return True
        tele = self.store.get(alias)
        if tele is None:
            return False
        self._caps[alias] = tele.caps
        if tele.last_seen is not None:
            self._beats[alias] = tele.last_seen
            self._written[alias] = tele.last_seen
        return True

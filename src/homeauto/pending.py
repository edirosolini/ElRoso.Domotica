"""Una conversación a medio armar, y dónde espera.

El hilo guarda el comando que se está armando, todo lo que la persona escribió
para él, y qué datos ya se preguntaron. Vive en SQLite para que un reinicio no
lo pierda, y vence.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

# Suficiente para dejar el teléfono un rato, poco para que un "sí" suelto no
# caiga sobre una pregunta de otro momento del día.
TTL = timedelta(minutes=10)

# Decirlo es mejor que esperar diez minutos. «cancelá» no está a propósito:
# /cancelar lleva un número y usar la misma palabra para tirar un borrador se
# leería como cancelar una alarma ya puesta.
DROP_WORDS = (
    "olvidalo", "olvídalo", "olvidate", "olvídate", "dejalo", "déjalo",
    "nada", "no importa", "dejá", "deja", "nada que ver",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS pending (
    chat_id  INTEGER PRIMARY KEY,
    command  TEXT NOT NULL,
    thread   TEXT NOT NULL,
    asked    TEXT NOT NULL,
    asked_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Pending:
    """El comando que se está armando para un chat."""

    command: str
    thread: str
    asked: tuple[str, ...]
    asked_at: datetime


class PendingStore:
    """Una fila por chat: la séptima tabla de `jobs.db`, dueña de su esquema."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, chat_id: int) -> Pending | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT command, thread, asked, asked_at FROM pending WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if not row:
            return None
        try:
            asked_at = datetime.fromisoformat(row["asked_at"])
        except ValueError:
            return None
        asked = tuple(name for name in row["asked"].split(",") if name)
        return Pending(row["command"], row["thread"], asked, asked_at)

    def set(self, chat_id: int, pending: Pending) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO pending (chat_id, command, thread, asked, asked_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET command = excluded.command, "
                "thread = excluded.thread, asked = excluded.asked, "
                "asked_at = excluded.asked_at",
                (
                    chat_id,
                    pending.command,
                    pending.thread,
                    ",".join(pending.asked),
                    pending.asked_at.isoformat(),
                ),
            )

    def clear(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pending WHERE chat_id = ?", (chat_id,))


class Conversation:
    """El comando a medio armar de cada chat, y hasta cuándo vale.

    Como `quiet.Hush`, el vencimiento se resuelve al salir: quien pregunta
    recibe algo válido o nada, y nadie aguas abajo chequea dos cosas.
    """

    def __init__(
        self,
        store: PendingStore,
        ttl: timedelta = TTL,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.store = store
        self.ttl = ttl
        self.clock = clock

    def get(self, chat_id: int) -> Pending | None:
        pending = self.store.get(chat_id)
        if pending is None:
            return None
        if self.clock() - pending.asked_at > self.ttl:
            self.store.clear(chat_id)
            return None
        return pending

    def remember(self, chat_id: int, command: str, thread: str, asked: tuple[str, ...]) -> None:
        self.store.set(chat_id, Pending(command, thread, tuple(asked), self.clock()))

    def forget(self, chat_id: int) -> None:
        self.store.clear(chat_id)

    @staticmethod
    def dropped(text: str) -> bool:
        """Si el mensaje significa «olvidalo», antes de pagar la llamada al modelo."""
        return " ".join(text.lower().split()).strip(".!¡") in DROP_WORDS

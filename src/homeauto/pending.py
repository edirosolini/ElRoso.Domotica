"""A conversation left half finished, and where it waits.

When a command comes in without a datum it needs, the bot asks for it — and the
answer arrives as another message, with nothing tying it to the question. This
is that thread: the command being built, everything the person has written for
it, and which data were already asked for.

🔴 It lives in SQLite, not in memory, for the same reason the silence asked for
by hand does: a restart in the middle of "¿a qué hora?" would leave the answer
with nowhere to land, and the person would be answering a question the house
already forgot.

🔴 It expires. Without a deadline, a "sí" tomorrow morning answers a question
from last night, and the alarm that comes out of it is nobody's.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

# Long enough to walk away from the phone, short enough that a stray "sí" does
# not land on a question from another moment of the day.
TTL = timedelta(minutes=10)

# Saying it out loud beats waiting ten minutes. «cancelá» is not here on
# purpose: /cancelar takes a number and dropping a half-built alarm with the
# same word would read as cancelling a scheduled one.
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
    """The command being built for one chat."""

    command: str
    thread: str
    asked: tuple[str, ...]
    asked_at: datetime


class PendingStore:
    """One row per chat: the seventh table of `jobs.db`, and it owns its schema."""

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
    """The half-built command of each chat, and when it stops counting.

    Like `quiet.Hush`, the expiry is resolved on the way out: whoever asks gets
    either something still valid or nothing, and nobody downstream has to check
    a second thing.
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
        """Whether the message means «forget it», before paying for the model."""
        return " ".join(text.lower().split()).strip(".!¡") in DROP_WORDS

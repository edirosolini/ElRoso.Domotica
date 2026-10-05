"""El nombre de cada chat de la casa, como lo muestra Telegram."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    chat_id INTEGER PRIMARY KEY,
    name    TEXT    NOT NULL
);
"""


def display_name(chat_id: int, names: dict[int, str]) -> str:
    """El nombre guardado del chat, o «Chat <id>» si todavía no escribió."""
    return names.get(chat_id) or f"Chat {chat_id}"


class People:
    """Anota el nombre de quien escribe, solo si su chat es de la casa."""

    def __init__(self, store: "PeopleStore", chat_ids):
        self.store = store
        self.chat_ids = frozenset(chat_ids)

    def meet(self, chat_id: int, name: str) -> None:
        if chat_id in self.chat_ids:
            self.store.remember(chat_id, name)


class PeopleStore:
    """Una fila por chat con el último nombre visto, dueña de su esquema."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(self, chat_id: int, name: str) -> None:
        """Guarda el nombre del chat; uno vacío no pisa al que había."""
        name = name.strip()
        if not name:
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO people (chat_id, name) VALUES (?, ?)"
                " ON CONFLICT(chat_id) DO UPDATE SET name = excluded.name",
                (chat_id, name),
            )

    def names(self) -> dict[int, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT chat_id, name FROM people").fetchall()
        return {row["chat_id"]: row["name"] for row in rows}

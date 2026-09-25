"""El aviso a los dueños cuando le escribe al bot alguien que no está en la lista."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable

from homeauto.config import Config

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS strangers (
    chat_id  INTEGER PRIMARY KEY,
    who      TEXT NOT NULL,
    told_at  TEXT NOT NULL
);
"""


class StrangerStore:
    """Los chats de los que ya se avisó, para avisar una sola vez."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def known(self, chat_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM strangers WHERE chat_id = ?", (chat_id,)).fetchone()
        return row is not None

    def remember(self, chat_id: int, who: str, at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO strangers (chat_id, who, told_at) VALUES (?, ?, ?)",
                (chat_id, who, at.isoformat()),
            )


class Strangers:
    def __init__(
        self,
        config: Config,
        store: StrangerStore,
        notify: Callable[[int, str], None],
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.config = config
        self.store = store
        self.notify = notify
        self.clock = clock

    def knock(self, chat_id: int, who: str) -> None:
        """Avisa a los dueños la primera vez que escribe un chat fuera de la lista."""
        if self.config.is_allowed(chat_id) or self.store.known(chat_id):
            return

        text = self._text(chat_id, who)
        told = False
        for owner in sorted(self.config.allowed_chat_ids):
            try:
                self.notify(owner, text)
                told = True
            except Exception:  # noqa: BLE001 - un dueño sin avisar no frena al otro
                log.exception("no pude avisar al chat %s del chat nuevo %s", owner, chat_id)

        if told:
            self.store.remember(chat_id, who, self.clock())

    def _text(self, chat_id: int, who: str) -> str:
        allowed = ",".join(str(i) for i in sorted(self.config.allowed_chat_ids | {chat_id}))
        return (
            f"🚪 Alguien nuevo le escribió al bot: {who}\n"
            f"ID: {chat_id}\n\n"
            "Para dejarlo entrar, cambiá la línea en /etc/domotica/domotica.env y reiniciá "
            "el servicio:\n\n"
            f"ALLOWED_CHAT_IDS={allowed}"
        )

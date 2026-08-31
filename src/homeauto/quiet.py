"""The hours when the house sleeps, and the silence someone asks for by hand.

Inside the window nothing is said out loud: the message still reaches Telegram,
so nothing is lost, but the speakers stay quiet. An alarm shouting in a bedroom
at three in the morning is how a system like this gets unplugged.

A nap and a meeting need the same thing for a couple of hours, so `Hush` adds a
window on top of the fixed ones. It answers the same questions `QuietHours`
does, which is why everything that consults the quiet window keeps working
without knowing that the silence can now be moved.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path


def _parse_clock(raw: str, field: str) -> time:
    raw = raw.strip()
    try:
        hour, _, minute = raw.partition(":")
        return time(int(hour), int(minute or 0))
    except ValueError as exc:
        raise ValueError(f"{field} no es una hora válida: '{raw}'") from exc


@dataclass(frozen=True)
class QuietHours:
    start: time
    end: time

    @classmethod
    def parse(cls, start: str, end: str) -> "QuietHours":
        return cls(start=_parse_clock(start, "inicio"), end=_parse_clock(end, "fin"))

    @property
    def enabled(self) -> bool:
        return self.start != self.end

    @property
    def label(self) -> str:
        return f"{self.start.strftime('%H:%M')}–{self.end.strftime('%H:%M')}"

    def is_quiet(self, moment: datetime) -> bool:
        if not self.enabled:
            return False

        now = moment.time()
        if self.start < self.end:
            return self.start <= now < self.end
        # The window crosses midnight: 23:00–07:00 is "late today or early tomorrow".
        return now >= self.start or now < self.end


SCHEMA = """
CREATE TABLE IF NOT EXISTS hush (
    id    INTEGER PRIMARY KEY CHECK (id = 1),
    until TEXT NOT NULL
);
"""


class HushStore:
    """One row: when the silence someone asked for runs out.

    It is stored, not kept in memory, because a restart in the middle of a nap
    would otherwise bring the house back talking.
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def until(self) -> datetime | None:
        with self._connect() as conn:
            row = conn.execute("SELECT until FROM hush WHERE id = 1").fetchone()
        if not row:
            return None
        try:
            return datetime.fromisoformat(row["until"])
        except ValueError:
            return None

    def set(self, moment: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO hush (id, until) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET until = excluded.until",
                (moment.isoformat(),),
            )

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM hush WHERE id = 1")


class Hush:
    """The resting hours plus a silence asked for by hand.

    Deliberately the same shape as `QuietHours`: whoever consults it — the
    announcer, the commands, the API, the house voice — asks `is_quiet()` and
    reads `label`, and none of them has to learn about the second rule.
    """

    def __init__(self, hours: QuietHours, store: HushStore, clock=datetime.now):
        self.hours = hours
        self.store = store
        self.clock = clock

    def until(self, moment: datetime | None = None) -> datetime | None:
        """When the manual silence ends, or None if there is none running."""
        moment = moment or self.clock()
        ends = self.store.until()
        if ends is None:
            return None
        if moment >= ends:
            # Expired: forget it here so nothing downstream has to check twice.
            self.store.clear()
            return None
        return ends

    def start(self, duration: timedelta) -> datetime:
        ends = self.clock() + duration
        self.store.set(ends)
        return ends

    def stop(self) -> bool:
        """True if there was a silence to cut short."""
        if self.until() is None:
            return False
        self.store.clear()
        return True

    @property
    def enabled(self) -> bool:
        return self.hours.enabled or self.until() is not None

    @property
    def label(self) -> str:
        ends = self.until()
        if ends is not None:
            return f"hasta las {ends.strftime('%H:%M')}, a pedido"
        return self.hours.label

    def is_quiet(self, moment: datetime) -> bool:
        return self.until(moment) is not None or self.hours.is_quiet(moment)

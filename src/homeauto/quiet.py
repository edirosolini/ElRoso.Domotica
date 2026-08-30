"""The hours when the house sleeps.

Inside the window nothing is said out loud: the message still reaches Telegram,
so nothing is lost, but the speakers stay quiet. An alarm shouting in a bedroom
at three in the morning is how a system like this gets unplugged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time


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

"""Warning about an event before it starts.

Runs on a loop. What matters is that it never announces the same occurrence
twice, and never shouts events that already began: after a restart, that would
be noise instead of a reminder.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from homeauto.agenda.ical import Event
from homeauto.agenda.seen import SeenStore
from homeauto.verbalize import number

log = logging.getLogger(__name__)

FORGET_AFTER_DAYS = 2


def announcement_for(event: Event, now: datetime) -> str:
    minutes = round((event.start - now).total_seconds() / 60)
    # In words: "en 1 minuto" was read out as "en uno minuto".
    if minutes <= 0:
        when = "ahora"
    else:
        unit = "minuto" if minutes == 1 else "minutos"
        when = f"en {number(minutes)} {unit}"

    text = f"Atención: {event.summary}, {when}"
    if event.location:
        text += f", en {event.location}"
    return text + "."


class EventWatcher:
    def __init__(
        self,
        calendar,
        announce: Callable[[str], None],
        seen: SeenStore,
        lead_minutes: int,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.calendar = calendar
        self.announce = announce
        self.seen = seen
        self.lead_minutes = lead_minutes
        self.clock = clock

    def check(self) -> list[Event]:
        now = self.clock()
        try:
            upcoming = self.calendar.between(now, now + timedelta(minutes=self.lead_minutes))
        except Exception as exc:  # noqa: BLE001 - el loop no puede morirse por esto
            log.warning("no pude mirar el calendario: %s", exc)
            return []

        announced = []
        for event in upcoming:
            if event.start < now or self.seen.was_seen(event.key):
                continue
            try:
                self.announce(announcement_for(event, now))
            except Exception:
                # Not marked: it gets another chance on the next round.
                log.exception("no pude avisar del evento %s", event.summary)
                continue
            self.seen.mark(event.key, now)
            announced.append(event)

        self.seen.forget_before(now - timedelta(days=FORGET_AFTER_DAYS))
        return announced

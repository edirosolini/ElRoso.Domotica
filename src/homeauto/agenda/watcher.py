"""Aviso de un evento antes de que empiece.

Corre en bucle. Lo que importa es que nunca anuncia dos veces la misma
ocurrencia, y nunca grita eventos que ya empezaron: tras un reinicio eso sería
ruido en vez de recordatorio.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from homeauto.agenda.ical import Event
from homeauto.agenda.seen import SeenStore
from homeauto.verbalize import number
from homeauto.polish import as_is

log = logging.getLogger(__name__)

FORGET_AFTER_DAYS = 2


def announcement_for(event: Event, now: datetime) -> str:
    minutes = round((event.start - now).total_seconds() / 60)
    # En palabras: Piper lee un dígito como cardinal masculino suelto.
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
        polish: Callable[..., str] = as_is,
    ):
        self.calendar = calendar
        self.announce = announce
        self.seen = seen
        self.lead_minutes = lead_minutes
        self.clock = clock
        self.polish = polish

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
                self.announce(
                    self.polish(announcement_for(event, now), must_keep=[event.summary])
                )
            except Exception:
                # No se marca: se reintenta en la vuelta siguiente.
                log.exception("no pude avisar del evento %s", event.summary)
                continue
            self.seen.mark(event.key, now)
            announced.append(event)

        self.seen.forget_before(now - timedelta(days=FORGET_AFTER_DAYS))
        return announced

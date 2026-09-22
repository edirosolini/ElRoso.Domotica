"""Contesta "qué tengo" con las palabras que usaría una persona."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from homeauto.agenda.speech import describe
from homeauto.polish import as_is

TODAY_WORDS = ("hoy", "")
TOMORROW_WORDS = ("mañana", "manana")


class AgendaService:
    def __init__(
        self,
        calendar,
        clock: Callable[[], datetime] = datetime.now,
        polish: Callable[..., str] = as_is,
    ):
        self.calendar = calendar
        self.clock = clock
        # Se pule antes de hablarlo, nunca se reescribe el dato: los títulos
        # viajan como términos que tienen que sobrevivir intactos.
        self.polish = polish

    def _say(self, events, label: str, place: bool = True) -> str:
        # Por argumento, no en self: el job del resumen y un /agenda del chat
        # corren en hilos distintos al mismo tiempo.
        return self.polish(
            describe(events, label=label, place=place),
            must_keep=[event.summary for event in events],
        )

    def spoken(self, when: str = "") -> str:
        word = when.strip().lower()
        now = self.clock()

        if word in TODAY_WORDS:
            # Lo que queda, no lo que ya pasó.
            return self._say(self.calendar.rest_of_day(now), label="hoy")
        if word in TOMORROW_WORDS:
            return self._say(self.calendar.day(now + timedelta(days=1)), label="mañana")

        raise ValueError(f"No entiendo '{when}'. Probá con hoy o mañana.")

    def briefing(self) -> str:
        """El día entero, para el resumen de la mañana: la hora y el título.

        Sin el lugar: escuchado junto al resto del resumen era lo que lo hacía
        arrastrarse. /agenda lo sigue diciendo.
        """
        return self._say(self.calendar.day(self.clock()), label="hoy", place=False)

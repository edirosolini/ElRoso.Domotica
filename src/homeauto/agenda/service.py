"""Answering "what do I have" in the words a person would use."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from homeauto.agenda.speech import describe

TODAY_WORDS = ("hoy", "")
TOMORROW_WORDS = ("mañana", "manana")


class AgendaService:
    def __init__(self, calendar, clock: Callable[[], datetime] = datetime.now):
        self.calendar = calendar
        self.clock = clock

    def spoken(self, when: str = "") -> str:
        word = when.strip().lower()
        now = self.clock()

        if word in TODAY_WORDS:
            # What is left, not what already happened.
            return describe(self.calendar.rest_of_day(now), label="hoy")
        if word in TOMORROW_WORDS:
            return describe(self.calendar.day(now + timedelta(days=1)), label="mañana")

        raise ValueError(f"No entiendo '{when}'. Probá con hoy o mañana.")

    def briefing(self) -> str:
        """The whole day, for the morning summary."""
        return describe(self.calendar.day(self.clock()), label="hoy")

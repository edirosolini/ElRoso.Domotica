"""Answering "what do I have" in the words a person would use."""

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
        # Reworded before it is spoken, never re-informed: the titles travel as
        # terms that have to survive untouched.
        self.polish = polish

    def _say(self, events, label: str) -> str:
        # The label travels as an argument on purpose: the briefing job and a
        # /agenda from the chat run in different threads at the same time, and
        # anything kept on self would let one overwrite the other's day.
        return self.polish(
            describe(events, label=label),
            must_keep=[event.summary for event in events],
        )

    def spoken(self, when: str = "") -> str:
        word = when.strip().lower()
        now = self.clock()

        if word in TODAY_WORDS:
            # What is left, not what already happened.
            return self._say(self.calendar.rest_of_day(now), label="hoy")
        if word in TOMORROW_WORDS:
            return self._say(self.calendar.day(now + timedelta(days=1)), label="mañana")

        raise ValueError(f"No entiendo '{when}'. Probá con hoy o mañana.")

    def briefing(self) -> str:
        """The whole day, for the morning summary."""
        return self._say(self.calendar.day(self.clock()), label="hoy")

"""Turning a list of events into something worth hearing out loud."""

from __future__ import annotations

from homeauto.agenda.ical import Event
from homeauto.verbalize import FEMININE, clock, number


def _clock(event: Event) -> str:
    # 🔴 In words, never as digits: the synthesizer reads "21:15" as a number.
    return f"a {clock(event.start.hour, event.start.minute)}"


def _one(event: Event, place: bool = True) -> str:
    when = "todo el día" if event.all_day else _clock(event)
    text = f"{when.capitalize()}, {event.summary}"
    if place and event.location:
        text += f", en {event.location}"
    return text + "."


def describe(events: list[Event], label: str, place: bool = True) -> str:
    """One or two sentences, written to be heard rather than read.

    `place` is off in the morning summary. Heard next to the weather, the
    economy and whatever is down, "en Sanatorio Colegiales" was what made it
    drag; asked for on purpose with /agenda, where it is on, it is the answer.
    """
    if not events:
        return f"No tenés nada agendado {label}."

    # All-day things frame the day, so they go first regardless of their hour.
    ordered = sorted(events, key=lambda event: (not event.all_day, event.start))

    count = len(ordered)
    # "cosa" is feminine: a bare digit here came out as "tenés uno cosa".
    things = "cosa" if count == 1 else "cosas"
    heading = f"{label.capitalize()} tenés {number(count, FEMININE)} {things}."
    return " ".join([heading] + [_one(event, place) for event in ordered])

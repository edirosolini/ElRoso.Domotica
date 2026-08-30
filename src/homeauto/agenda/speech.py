"""Turning a list of events into something worth hearing out loud."""

from __future__ import annotations

from homeauto.agenda.ical import Event


def _clock(event: Event) -> str:
    # On the hour, saying the minutes adds nothing: "a las 10", not "a las 10:00".
    if event.start.minute == 0:
        return f"a las {event.start.hour}"
    return f"a las {event.start.strftime('%H:%M')}"


def _one(event: Event) -> str:
    when = "todo el día" if event.all_day else _clock(event)
    text = f"{when.capitalize()}, {event.summary}"
    if event.location:
        text += f", en {event.location}"
    return text + "."


def describe(events: list[Event], label: str) -> str:
    """One or two sentences, written to be heard rather than read."""
    if not events:
        return f"No tenés nada agendado {label}."

    # All-day things frame the day, so they go first regardless of their hour.
    ordered = sorted(events, key=lambda event: (not event.all_day, event.start))

    count = len(ordered)
    heading = f"{label.capitalize()} tenés 1 cosa." if count == 1 else f"{label.capitalize()} tenés {count} cosas."
    return " ".join([heading] + [_one(event) for event in ordered])

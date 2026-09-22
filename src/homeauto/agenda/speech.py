"""Convierte una lista de eventos en algo que valga la pena escuchar."""

from __future__ import annotations

from homeauto.agenda.ical import Event
from homeauto.verbalize import FEMININE, clock, number


def _clock(event: Event) -> str:
    # En palabras, nunca en dígitos: el sintetizador lee "21:15" como un número.
    return f"a {clock(event.start.hour, event.start.minute)}"


def _one(event: Event, place: bool = True) -> str:
    when = "todo el día" if event.all_day else _clock(event)
    text = f"{when.capitalize()}, {event.summary}"
    if place and event.location:
        text += f", en {event.location}"
    return text + "."


def describe(events: list[Event], label: str, place: bool = True) -> str:
    """Una o dos oraciones, escritas para escucharse y no para leerse.

    `place` va apagado en el resumen de la mañana y encendido en /agenda, que
    se pide a propósito.
    """
    if not events:
        return f"No tenés nada agendado {label}."

    # Lo de día completo enmarca el día, así que va primero sin importar la hora.
    ordered = sorted(events, key=lambda event: (not event.all_day, event.start))

    count = len(ordered)
    # "cosa" es femenino, así que el número concuerda con él.
    things = "cosa" if count == 1 else "cosas"
    heading = f"{label.capitalize()} tenés {number(count, FEMININE)} {things}."
    return " ".join([heading] + [_one(event, place) for event in ordered])

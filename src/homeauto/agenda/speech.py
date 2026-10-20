"""Convierte una lista de eventos en algo que valga la pena escuchar."""

from __future__ import annotations

from homeauto.agenda.ical import Event
from homeauto.verbalize import FEMININE, clock, number


def _clock(event: Event) -> str:
    # En palabras, nunca en dígitos: el sintetizador lee "21:15" como un número.
    return f"a {clock(event.start.hour, event.start.minute)}"


def _when(event: Event) -> str:
    return "todo el día" if event.all_day else _clock(event)


def _what(event: Event, place: bool) -> str:
    """El título literal, con el lugar si va y lo tiene."""
    if place and event.location:
        return f"{event.summary}, en {event.location}"
    return event.summary


def _sentence(*parts: str) -> str:
    """Une las partes no vacías con mayúscula inicial y punto final."""
    text = " ".join(part for part in parts if part)
    return text[:1].upper() + text[1:] + "."


def describe(events: list[Event], label: str, place: bool = True) -> str:
    """Una sola oración, escrita para escucharse y no para leerse.

    `place` va apagado en el resumen de la mañana y encendido en /agenda, que
    se pide a propósito.
    """
    if not events:
        return f"No tenés nada agendado {label}."

    # Lo de día completo enmarca el día, así que va primero sin importar la hora.
    ordered = sorted(events, key=lambda event: (not event.all_day, event.start))

    if len(ordered) == 1:
        event = ordered[0]
        return _sentence(label, _when(event), "tenés", _what(event, place))

    items = [f"{_when(event)}, {_what(event, place)}" for event in ordered]
    items[-1] = f"y {items[-1]}"
    # El número va en femenino, para concordar con «cosas».
    heading = f"tenés {number(len(ordered), FEMININE)} cosas:"
    return _sentence(label, heading, "; ".join(items))

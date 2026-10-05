"""Las reglas de lo programado: qué tipo es y cuándo suena por primera vez."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from homeauto.schedule.month import ALARM_ITEM, REMINDER_ITEM, TIMER_ITEM
from homeauto.schedule.store import ALARM, DAILY, ONCE, REMINDER, REPEATS, WEEKLY
from homeauto.timespec import next_weekday


class SpecError(ValueError):
    """Lo pedido no se puede programar; el texto es para la persona."""


def classify(item: str, repeat: str) -> tuple[str, str]:
    """El tipo de la pantalla (alarma, recordatorio, timer) como kind y repetición."""
    if repeat not in REPEATS:
        raise SpecError("No conozco esa repetición.")
    if item == ALARM_ITEM:
        return ALARM, repeat
    if item == TIMER_ITEM:
        if repeat != ONCE:
            raise SpecError("Un timer suena una sola vez.")
        return REMINDER, ONCE
    if item == REMINDER_ITEM:
        if repeat == ONCE:
            raise SpecError(
                "Un recordatorio repite: elegí todos los días o algunos días. "
                "Para una sola vez, un timer."
            )
        return REMINDER, repeat
    raise SpecError("No conozco ese tipo de aviso.")


def resolve(
    repeat: str, when: datetime, now: datetime, days: Iterable[int] | None = None
) -> datetime:
    """La primera vez que suena lo pedido para `when`, o SpecError si no puede sonar."""
    if repeat == ONCE:
        if when <= now:
            raise SpecError("Esa hora ya pasó.")
        return when
    if when <= now:
        # La misma hora, el primer día en que todavía no pasó.
        when += timedelta(days=(now - when).days + 1)
    if repeat == DAILY:
        return when
    if repeat == WEEKLY:
        chosen = tuple(days or ())
        if not chosen:
            raise SpecError("Con días de la semana necesito los días.")
        if any(day not in range(1, 8) for day in chosen):
            raise SpecError("Algún día de la semana no existe.")
        return next_weekday(when, chosen)
    raise SpecError("No conozco esa repetición.")

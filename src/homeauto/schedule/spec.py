"""Las reglas de lo programado: qué tipo es y cuándo suena por primera vez."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Callable, Iterable

from homeauto.schedule.month import ALARM_ITEM, REMINDER_ITEM, TIMER_ITEM
from homeauto.schedule.store import (
    ALARM, DAILY, MONTHLY, ONCE, REMINDER, REPEATS, WEEKLY, Job, next_month, on_monthday,
)
from homeauto.timespec import format_weekdays, next_weekday
from homeauto.verbalize import cardinal

if TYPE_CHECKING:
    from homeauto.holidays import Holiday

# El día más alto que tienen todos los meses.
SHORTEST_MONTH = 28
WORKING_DAYS = (1, 2, 3, 4, 5)


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
    repeat: str,
    when: datetime,
    now: datetime,
    days: Iterable[int] | None = None,
    monthday: int | None = None,
) -> datetime:
    """La primera vez que suena lo pedido para `when`, o SpecError si no puede sonar."""
    if repeat == MONTHLY:
        return _first_monthly(when, now, monthday)
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


def _first_monthly(when: datetime, now: datetime, monthday: int | None) -> datetime:
    """El primer `monthday` a la hora de `when` que no es antes de `when` ni de `now`."""
    if monthday is None:
        raise SpecError("Con mensual necesito el día del mes.")
    if monthday not in range(1, 32):
        raise SpecError("Ese día del mes no existe.")
    first = on_monthday(when.year, when.month, monthday, when)
    while first < when or first <= now:
        first = next_month(first, monthday)
    return first


def check_skip_holidays(repeat: str, skip_holidays: bool) -> None:
    """SpecError si se pide saltear feriados en algo que no repite por días de la semana."""
    if skip_holidays and repeat != WEEKLY:
        raise SpecError("Saltear feriados es solo para lo que repite por días de la semana.")


def skips(
    job: Job, day: date, holidays: Callable[[date], Holiday | None] | None
) -> Holiday | None:
    """El feriado por el que el job no suena ese día, o None si suena."""
    if holidays is None or not job.skip_holidays or not job.is_weekly:
        return None
    holiday = holidays(day)
    return holiday if holiday is not None and holiday.skips else None


def weekdays_label(days: Iterable[int], skip_holidays: bool = False) -> str:
    """Los días de un semanal para el chat, diciendo si saltea feriados."""
    days = sorted(days)
    if not skip_holidays:
        return format_weekdays(days)
    if days == list(WORKING_DAYS):
        return "días hábiles"
    return f"{format_weekdays(days)}, sin feriados"


def monthly_label(monthday: int) -> str:
    return f"el {monthday} de cada mes"


def repetition_label(job: Job) -> str:
    """Cómo repite un job, para el chat; vacío si suena una sola vez."""
    if job.repeat == DAILY:
        return "todos los días"
    if job.repeat == WEEKLY:
        return weekdays_label(job.weekdays, job.skip_holidays)
    if job.repeat == MONTHLY and job.monthday:
        return monthly_label(job.monthday)
    return ""


def ringing_label(job: Job) -> str:
    """Cómo repite un job en el aviso de que sonó, sin dígitos; vacío si suena una sola vez."""
    if job.repeat == DAILY:
        return "de todos los días"
    if job.repeat == WEEKLY:
        return f"de {format_weekdays(job.weekdays)}"
    if job.repeat == MONTHLY and job.monthday:
        return f"del {cardinal(job.monthday)} de cada mes"
    return ""


def short_month_note(monthday: int) -> str:
    """El aviso de qué pasa los meses que no tienen ese día; vacío si todos lo tienen."""
    if monthday <= SHORTEST_MONTH:
        return ""
    return f"Los meses que no tienen {monthday}, el último día."

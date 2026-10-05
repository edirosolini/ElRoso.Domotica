"""El mes de lo programado: lo que ya sonó, del historial, y lo que va a sonar, de los jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable

from homeauto.schedule.history import CANCEL, DONE, SNOOZE, Entry
from homeauto.schedule.store import ALARM, DAILY, ONCE, WEEKLY, Job, next_run
from homeauto.timespec import next_weekday

ALARM_ITEM = "alarm"
REMINDER_ITEM = "reminder"
TIMER_ITEM = "timer"


@dataclass(frozen=True)
class Item:
    at: datetime
    kind: str
    message: str
    past: bool = False
    silent: bool = False
    done: bool = False
    done_by: str | None = None
    nags: int = 0
    snoozed: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class Day:
    date: date
    in_month: bool
    today: bool
    items: list[Item] = field(default_factory=list)


@dataclass(frozen=True)
class MonthView:
    year: int
    month: int
    weeks: list[list[Day]]
    previous: tuple[int, int]
    following: tuple[int, int]

    @property
    def days(self) -> list[Day]:
        """Los días del mes que tienen algo, en orden."""
        return [day for week in self.weeks for day in week if day.in_month and day.items]


def item_kind(kind: str, repeat: str) -> str:
    """El tipo de ítem: alarma, recordatorio, o timer si el recordatorio no repite."""
    if kind == ALARM:
        return ALARM_ITEM
    return TIMER_ITEM if repeat == ONCE else REMINDER_ITEM


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """El primer instante del mes y el primero del mes siguiente."""
    start = datetime(year, month, 1)
    following = _shift(year, month, 1)
    return start, datetime(*following, 1)


def occurrences(jobs: Iterable[Job], year: int, month: int, now: datetime) -> list[Item]:
    """Lo que los jobs van a hacer sonar en el mes, desde `now` en adelante."""
    start, end = month_bounds(year, month)
    since = max(start, now)
    found = []
    for job in jobs:
        kind = item_kind(job.kind, job.repeat)
        at = _first_from(job, since)
        while at is not None and at < end:
            if at >= since:
                found.append(Item(at=at, kind=kind, message=job.message))
            at = next_run(job, at)
    return sorted(found, key=lambda item: item.at)


def _first_from(job: Job, since: datetime) -> datetime | None:
    """La primera ocurrencia candidata del job a partir del día de `since`."""
    at = job.when
    if at >= since or job.repeat not in (DAILY, WEEKLY):
        return at
    at += timedelta(days=(since - at).days)
    return next_weekday(at, job.weekdays) if job.repeat == WEEKLY else at


def _from_history(entry: Entry) -> Item:
    return Item(
        at=entry.fired_at,
        kind=item_kind(entry.kind, entry.repeat),
        message=entry.message,
        past=True,
        silent=not entry.announced,
        done=entry.closed == DONE,
        done_by=entry.done_by,
        nags=entry.nags,
        snoozed=entry.closed == SNOOZE,
        cancelled=entry.closed == CANCEL,
    )


def month_view(
    jobs: Iterable[Job], entries: Iterable[Entry], year: int, month: int, now: datetime
) -> MonthView:
    """La grilla del mes, de lunes a domingo, con lo sonado antes de `now` y lo agendado después."""
    start, end = month_bounds(year, month)
    past = [_from_history(e) for e in entries if start <= e.fired_at < min(end, now)]
    items = sorted(past + occurrences(jobs, year, month, now), key=lambda item: item.at)
    by_day: dict[date, list[Item]] = {}
    for item in items:
        by_day.setdefault(item.at.date(), []).append(item)

    first = start.date() - timedelta(days=start.weekday())
    last_day = (end - timedelta(days=1)).date()
    last = last_day + timedelta(days=6 - last_day.weekday())
    weeks = []
    current = first
    while current <= last:
        week = []
        for _ in range(7):
            week.append(
                Day(
                    date=current,
                    in_month=current.month == month,
                    today=current == now.date(),
                    items=by_day.get(current, []) if current.month == month else [],
                )
            )
            current += timedelta(days=1)
        weeks.append(week)
    return MonthView(
        year=year,
        month=month,
        weeks=weeks,
        previous=_shift(year, month, -1),
        following=_shift(year, month, 1),
    )


def _shift(year: int, month: int, step: int) -> tuple[int, int]:
    """El año y el mes a `step` meses de distancia."""
    index = year * 12 + (month - 1) + step
    return index // 12, index % 12 + 1

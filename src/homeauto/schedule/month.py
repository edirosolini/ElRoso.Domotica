"""Lo programado en un rango: lo que ya sonó, del historial, y lo que va a sonar, de los jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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


def item_kind(kind: str, repeat: str) -> str:
    """El tipo de ítem: alarma, recordatorio, o timer si el recordatorio no repite."""
    if kind == ALARM:
        return ALARM_ITEM
    return TIMER_ITEM if repeat == ONCE else REMINDER_ITEM


def occurrences_between(
    jobs: Iterable[Job], start: datetime, end: datetime, now: datetime
) -> list[Item]:
    """Lo que los jobs van a hacer sonar entre `start` y `end`, desde `now` en adelante."""
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


def from_history(entry: Entry) -> Item:
    """Lo que ya sonó, con cómo terminó."""
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

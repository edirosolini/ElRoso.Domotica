"""Timers and alarms: what to say, when, and what to do after saying it.

The actual clock lives behind the `timer` interface, so this logic is tested
without waiting for wall time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, Iterable, Protocol

from homeauto.schedule.store import DAILY, ONCE, WEEKLY, Job, Store
from homeauto.timespec import next_weekday

log = logging.getLogger(__name__)


class Timer(Protocol):
    def schedule(self, key: str, when: datetime, action: Callable[[], None]) -> None: ...
    def unschedule(self, key: str) -> None: ...


class Reminders:
    def __init__(self, store: Store, timer: Timer, announce: Callable[[Job], None]):
        self.store = store
        self.timer = timer
        self.announce = announce

    def start(self, now: datetime | None = None) -> None:
        """Re-arm everything after a restart, firing whatever was missed."""
        now = now or datetime.now()
        for job in self.store.pending():
            if job.when <= now:
                log.info("disparando job %s que venció mientras estábamos caídos", job.id)
                self._fire(job.id)
            else:
                self._arm(job)

    def add(
        self,
        chat_id: int,
        when: datetime,
        message: str,
        repeat: str = ONCE,
        device: str | None = None,
        days: Iterable[int] | None = None,
    ) -> Job:
        job = self.store.add(chat_id, when, message, repeat, device, days)
        self._arm(job)
        return job

    def list(self, chat_id: int) -> list[Job]:
        return self.store.pending(chat_id=chat_id)

    def cancel(self, chat_id: int, job_id: int) -> bool:
        job = self.store.get(job_id)
        if job is None or job.chat_id != chat_id:
            return False
        self.timer.unschedule(str(job_id))
        return self.store.remove(job_id)

    def _arm(self, job: Job) -> None:
        self.timer.schedule(str(job.id), job.when, lambda: self._fire(job.id))

    def _fire(self, job_id: int) -> None:
        job = self.store.get(job_id)
        if job is None:  # cancelled between the arming and the firing
            return

        try:
            self.announce(job)
        except Exception:
            # A speaker that is off must not take the schedule down with it.
            log.exception("no se pudo anunciar el job %s", job_id)

        next_time = self._next_run(job)
        if next_time is None:
            self.timer.unschedule(str(job_id))
            self.store.remove(job_id)
        else:
            self.store.reschedule(job_id, next_time)
            self._arm(self.store.get(job_id))

    @staticmethod
    def _next_run(job: Job) -> datetime | None:
        """When a repeating job fires again; None if it was a one-shot."""
        if job.repeat == DAILY:
            return job.when + timedelta(days=1)
        if job.repeat == WEEKLY:
            # Start from the day after, or it would match today all over again.
            return next_weekday(job.when + timedelta(days=1), job.weekdays)
        return None

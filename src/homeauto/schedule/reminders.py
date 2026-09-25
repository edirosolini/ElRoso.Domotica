"""Timers y alarmas: qué decir, cuándo, y qué hacer después de decirlo.

El reloj de verdad vive detrás de la interfaz `timer`, así que esta lógica se
prueba sin esperar tiempo real.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, Iterable, Protocol

from homeauto.schedule.fired import FiredStore
from homeauto.schedule.store import DAILY, ONCE, WEEKLY, Job, Store
from homeauto.timespec import next_weekday

log = logging.getLogger(__name__)

# Hasta cuánto después de sonar se puede posponer una alarma.
SNOOZE_WINDOW = timedelta(minutes=30)


class Timer(Protocol):
    def schedule(self, key: str, when: datetime, action: Callable[[], None]) -> None: ...
    def unschedule(self, key: str) -> None: ...


class Reminders:
    def __init__(
        self,
        store: Store,
        timer: Timer,
        announce: Callable[[Job], None],
        fired: FiredStore | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.store = store
        self.timer = timer
        self.announce = announce
        self.fired = fired
        self.clock = clock

    def start(self, now: datetime | None = None) -> None:
        """Rearma todo tras un reinicio, disparando lo que se haya perdido."""
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

    def snooze(self, chat_id: int, delay: timedelta) -> Job | None:
        """Repite dentro de `delay` lo último que sonó en el chat, o None si no hay nada reciente."""
        if self.fired is None:
            return None
        last = self.fired.last(chat_id)
        now = self.clock()
        if last is None or now - last.at > SNOOZE_WINDOW:
            return None
        self.fired.forget(chat_id)
        return self.add(chat_id, now + delay, last.message, device=last.device)

    def _arm(self, job: Job) -> None:
        self.timer.schedule(str(job.id), job.when, lambda: self._fire(job.id))

    def _fire(self, job_id: int) -> None:
        job = self.store.get(job_id)
        if job is None:  # cancelled between the arming and the firing
            return

        # Antes de anunciar: el botón de posponer llega con el aviso.
        if self.fired is not None:
            self.fired.remember(job.chat_id, job.message, job.device, self.clock())

        try:
            self.announce(job)
        except Exception:
            # Un parlante apagado no puede llevarse puesta la agenda.
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
        """Cuándo vuelve a disparar un job repetido; None si era de una sola vez."""
        if job.repeat == DAILY:
            return job.when + timedelta(days=1)
        if job.repeat == WEEKLY:
            # Se busca desde el día siguiente, o volvería a caer en el mismo día.
            return next_weekday(job.when + timedelta(days=1), job.weekdays)
        return None

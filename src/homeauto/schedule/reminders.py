"""Timers, alarmas y recordatorios: qué decir, cuándo, y qué hacer después de decirlo.

El reloj de verdad vive detrás de la interfaz `timer`, así que esta lógica se
prueba sin esperar tiempo real.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, Iterable, Protocol

from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.history import CANCEL, SNOOZE, HistoryStore
from homeauto.schedule.store import ALARM, DAILY, ONCE, WEEKLY, Job, Store
from homeauto.timespec import next_weekday

log = logging.getLogger(__name__)

# Hasta cuánto después de sonar se puede posponer una alarma.
SNOOZE_WINDOW = timedelta(minutes=30)

# Cada cuánto y cuántas veces vuelve a avisar por el chat un recordatorio sin «Hecho».
NAG_DELAY = timedelta(minutes=5)
NAG_LIMIT = 3


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
        chat_ids: Iterable[int] = (),
        awaiting: AwaitingStore | None = None,
        notify: Callable[..., None] | None = None,
        nag_actions: tuple[tuple[str, str], ...] = (),
        history: HistoryStore | None = None,
    ):
        self.store = store
        self.timer = timer
        self.announce = announce
        self.fired = fired
        self.awaiting = awaiting
        self.history = history
        self.notify = notify
        self.clock = clock
        # Los chats que pueden posponer lo que sonó; vacío es solo el que lo pidió.
        self.chat_ids = list(chat_ids)
        # Botones del re-aviso; `{job}` se reemplaza por su número.
        self.nag_actions = nag_actions

    def start(self, now: datetime | None = None) -> None:
        """Rearma todo tras un reinicio, disparando lo que se haya perdido."""
        now = now or datetime.now()
        if self._nags():
            for wait in self.awaiting.due_nags():
                job = self.store.get(wait.job_id)
                chat_id = job.chat_id if job else None
                if wait.next_nag <= now:
                    self._nag(wait.job_id, chat_id)
                else:
                    self._arm_nag(wait.job_id, chat_id, wait.next_nag)
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
        kind: str = ALARM,
    ) -> Job:
        job = self.store.add(chat_id, when, message, repeat, device, days, kind)
        self._arm(job)
        return job

    def list(self, chat_id: int) -> list[Job]:
        return self.store.pending(chat_id=chat_id)

    def cancel(self, chat_id: int, job_id: int) -> bool:
        job = self.store.get(job_id)
        if job is None or job.chat_id != chat_id:
            return False
        self.timer.unschedule(str(job_id))
        if self._close_wait(job_id):
            now = self.clock()
            self._write_history(lambda history: history.mark_closed(job_id, CANCEL, now))
        return self.store.remove(job_id)

    def snooze(self, chat_id: int, delay: timedelta) -> Job | None:
        """Repite dentro de `delay` lo último que sonó en el chat, o None si no hay nada reciente."""
        if self.fired is None:
            return None
        last = self.fired.last(chat_id)
        now = self.clock()
        if last is None or now - last.at > SNOOZE_WINDOW:
            return None
        for chat in self._audience(chat_id):
            self.fired.forget(chat)
        if last.job_id is not None:
            self._close_wait(last.job_id)
            self._write_history(lambda history: history.mark_closed(last.job_id, SNOOZE, now))
        return self.add(chat_id, now + delay, last.message, device=last.device, kind=last.kind)

    def done(self, chat_id: int, job_id: int, who: str) -> str | None:
        """Cierra un recordatorio que sonó y avisa al resto; None si ya estaba cerrado."""
        if self.awaiting is None:
            return None
        message = self.awaiting.take(job_id)
        self.timer.unschedule(_nag_key(job_id))
        if message is None:
            return None
        now = self.clock()
        self._write_history(lambda history: history.mark_done(job_id, now, who))
        audience = self._audience(chat_id)
        for chat in audience:
            if self.fired is not None and (last := self.fired.last(chat)) and last.message == message:
                self.fired.forget(chat)
        for chat in audience:
            if chat == chat_id or self.notify is None:
                continue
            try:
                self.notify(chat, f"✅ {who} marcó hecho: «{message}»")
            except Exception:
                log.exception("no se pudo avisar al chat %s del hecho %s", chat, job_id)
        return message

    def _audience(self, chat_id: int | None) -> list[int]:
        return self.chat_ids or ([chat_id] if chat_id is not None else [])

    def _nags(self) -> bool:
        return self.awaiting is not None and self.notify is not None

    def _close_wait(self, job_id: int) -> bool:
        """Saca el job de la espera del «Hecho» y desagenda su re-aviso; True si esperaba."""
        self.timer.unschedule(_nag_key(job_id))
        if self.awaiting is None:
            return False
        return self.awaiting.take(job_id) is not None

    def _write_history(self, write: Callable[[HistoryStore], object]) -> None:
        """Escribe en el historial sin que una falla frene el aviso."""
        if self.history is None:
            return
        try:
            write(self.history)
        except Exception:
            log.exception("could not write to the fired history")

    def _arm_nag(self, job_id: int, chat_id: int | None, when: datetime) -> None:
        self.timer.schedule(_nag_key(job_id), when, lambda: self._nag(job_id, chat_id))

    def _nag(self, job_id: int, chat_id: int | None) -> None:
        """Vuelve a avisar por el chat un recordatorio que sigue sin «Hecho»."""
        wait = self.awaiting.get(job_id)
        if wait is None or wait.next_nag is None:
            return
        now = self.clock()
        if now - wait.fired_at > SNOOZE_WINDOW:
            self.awaiting.stop_nagging(job_id)
            return

        text = f"🔔 Sigue pendiente: «{wait.message}»"
        actions = tuple((label, data.format(job=job_id)) for label, data in self.nag_actions)
        for chat in self._audience(chat_id):
            try:
                if actions:
                    self.notify(chat, text, actions)
                else:
                    self.notify(chat, text)
            except Exception:
                log.exception("no se pudo re-avisar al chat %s del job %s", chat, job_id)
        self._write_history(lambda history: history.mark_nag(job_id))

        if wait.nags + 1 >= NAG_LIMIT:
            self.awaiting.mark_nagged(job_id, None)
        else:
            self.awaiting.mark_nagged(job_id, now + NAG_DELAY)
            self._arm_nag(job_id, chat_id, now + NAG_DELAY)

    def _arm(self, job: Job) -> None:
        self.timer.schedule(str(job.id), job.when, lambda: self._fire(job.id))

    def _fire(self, job_id: int) -> None:
        job = self.store.get(job_id)
        if job is None:  # cancelled between the arming and the firing
            return

        # Antes de anunciar: el botón de posponer llega con el aviso.
        if self.fired is not None:
            at = self.clock()
            for chat in self._audience(job.chat_id):
                self.fired.remember(chat, job.message, job.device, at, job.kind, job.id)
        if self.awaiting is not None and job.is_reminder:
            at = self.clock()
            next_nag = at + NAG_DELAY if self._nags() else None
            self.awaiting.remember(job.id, job.message, at, next_nag)
            if next_nag is not None:
                self._arm_nag(job.id, job.chat_id, next_nag)
        fired_at = self.clock()
        self._write_history(
            lambda history: history.record(
                job.id, job.chat_id, job.kind, job.repeat, job.message, fired_at
            )
        )

        try:
            self.announce(job)
        except Exception:
            # Un parlante apagado no puede llevarse puesta la agenda.
            log.exception("no se pudo anunciar el job %s", job_id)
        else:
            self._write_history(lambda history: history.mark_announced(job.id))

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


def _nag_key(job_id: int) -> str:
    """La clave del timer del re-aviso, distinta de la del job."""
    return f"nag:{job_id}"

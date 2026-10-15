"""Timers, alarmas y recordatorios: qué decir, cuándo, y qué hacer después de decirlo.

El reloj de verdad vive detrás de la interfaz `timer`, así que esta lógica se
prueba sin esperar tiempo real.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Callable, Iterable, Protocol

from homeauto.lists import SHOPPING
from homeauto.quiet import away_of
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.history import CANCEL, HOLIDAY, SNOOZE, HistoryStore
from homeauto.schedule.ringing import Ringing, RingingStore
from homeauto.schedule.rota import turn_for, with_turn
from homeauto.schedule.spec import skips
from homeauto.schedule.store import ALARM, ONCE, Job, Store, next_run

if TYPE_CHECKING:
    from homeauto.holidays import Holiday
    from homeauto.lists import ListStore
    from homeauto.schedule.stock import Stock, StockStore

log = logging.getLogger(__name__)

# Hasta cuánto después de sonar se puede posponer una alarma.
SNOOZE_WINDOW = timedelta(minutes=30)

# Cada cuánto y cuántas veces vuelve a avisar por el chat un recordatorio sin «Hecho».
NAG_DELAY = timedelta(minutes=5)
NAG_LIMIT = 3

# Una alarma vuelve a sonar un minuto después de terminar, hasta media hora desde que sonó.
RING_DELAY = timedelta(minutes=1)
RING_LIMIT = timedelta(minutes=30)
# Cada cuántas repeticiones se escribe al chat.
RING_WRITE_EVERY = 5


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
        ringing: RingingStore | None = None,
        stop_audio: Callable[[list[str]], None] | None = None,
        holidays: Callable[[date], Holiday | None] | None = None,
        stock: StockStore | None = None,
        lists: ListStore | None = None,
        quiet=None,
    ):
        self.store = store
        self.timer = timer
        self.announce = announce
        self.fired = fired
        self.awaiting = awaiting
        self.history = history
        self.ringing = ringing
        # Corta el audio en curso en esos equipos.
        self.stop_audio = stop_audio
        # El feriado de un día, leído de la caché local.
        self.holidays = holidays
        # Las dosis que quedan de cada remedio y la lista donde va lo que hay que comprar.
        self.stock = stock
        self.lists = lists
        # En vacaciones una alarma no se repite.
        self.quiet = quiet
        self.notify = notify
        self.clock = clock
        # Los chats que pueden posponer lo que sonó; vacío es solo el que lo pidió.
        self.chat_ids = list(chat_ids)
        # Botones del re-aviso; `{job}` se reemplaza por su número.
        self.nag_actions = nag_actions

    def start(self, now: datetime | None = None) -> None:
        """Rearma todo tras un reinicio, disparando lo que se haya perdido."""
        now = now or datetime.now()
        if self.ringing is not None:
            for ringing in self.ringing.all():
                if ringing.next_ring is None or ringing.next_ring <= now:
                    self._ring(ringing.job_id)
                else:
                    self._arm_ring(ringing.job_id, ringing.next_ring)
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
        monthday: int | None = None,
        skip_holidays: bool = False,
        stock_id: int | None = None,
    ) -> Job:
        job = self.store.add(
            chat_id, when, message, repeat, device, days, kind, monthday, skip_holidays, stock_id
        )
        self._arm(job)
        return job

    def update(
        self,
        job_id: int,
        when: datetime,
        message: str,
        repeat: str = ONCE,
        device: str | None = None,
        days: Iterable[int] | None = None,
        kind: str = ALARM,
        monthday: int | None = None,
        skip_holidays: bool = False,
    ) -> Job | None:
        """Reescribe un job y lo rearma; lo que ya sonó y espera su «Hecho» no se toca."""
        job = self.store.update(
            job_id, when, message, repeat, device, days, kind, monthday, skip_holidays
        )
        if job is None:
            return None
        self.timer.unschedule(str(job_id))
        self._arm(job)
        return job

    def list(self, chat_id: int | None) -> list[Job]:
        """Lo programado del chat, o de todos con None."""
        return self.store.pending(chat_id=chat_id)

    def get(self, job_id: int) -> Job | None:
        return self.store.get(job_id)

    def attach_stock(self, job_id: int, stock_id: int) -> bool:
        """Ata un job a un stock de remedio; False si el job ya no existe."""
        return self.store.attach_stock(job_id, stock_id)

    def set_rota(self, job_id: int, names: list[str] | None, start: date | None) -> bool:
        """Fija o quita los nombres que se turnan; False si el job ya no existe."""
        return self.store.set_rota(job_id, names, start)

    def cancel(self, chat_id: int | None, job_id: int, any_owner: bool = False) -> bool:
        """Borra un job del chat, o de cualquiera con `any_owner`; False si no estaba."""
        job = self.store.get(job_id)
        if job is None or (not any_owner and job.chat_id != chat_id):
            return False
        self.timer.unschedule(str(job_id))
        rang = self._stop_ringing(job_id) is not None
        if self._close_wait(job_id) or rang:
            now = self.clock()
            self._write_history(lambda history: history.mark_closed(job_id, CANCEL, now))
        return self.store.remove(job_id)

    def discard(self, chat_id: int, job_id: int, who: str) -> Job | None:
        """Borra un job de cualquiera y avisa al resto; None si ya no estaba."""
        job = self.store.get(job_id)
        if job is None or not self.cancel(chat_id, job_id, any_owner=True):
            return None
        for chat in self._audience(chat_id):
            if chat == chat_id or self.notify is None:
                continue
            try:
                self.notify(chat, f"🗑 {who} borró #{job_id}: «{job.message}»")
            except Exception:
                log.exception("no se pudo avisar al chat %s del borrado %s", chat, job_id)
        return job

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
            self._stop_ringing(last.job_id)
            self._close_wait(last.job_id)
            self._write_history(lambda history: history.mark_closed(last.job_id, SNOOZE, now))
        return self.add(
            chat_id, now + delay, last.message, device=last.device, kind=last.kind,
            stock_id=last.stock_id,
        )

    def done(self, chat_id: int, job_id: int, who: str) -> str | None:
        """Cierra un recordatorio que sonó y avisa al resto; None si ya estaba cerrado."""
        if self.awaiting is None:
            return None
        wait = self.awaiting.get(job_id)
        message = self.awaiting.take(job_id)
        self.timer.unschedule(_nag_key(job_id))
        if message is None:
            return None
        now = self.clock()
        self._write_history(lambda history: history.mark_done(job_id, now, who))
        if wait is not None and wait.stock_id is not None:
            self._take_dose(chat_id, wait.stock_id)
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

    def silence(self, chat_id: int, job_id: int, who: str) -> str | None:
        """Apaga la alarma que suena y avisa al resto; None si ya estaba apagada."""
        ringing = self._stop_ringing(job_id)
        if ringing is None:
            return None
        if self.stop_audio is not None:
            try:
                self.stop_audio(_ringing_job(ringing).devices)
            except Exception:
                log.exception("could not stop the audio of job %s", job_id)
        audience = self._audience(chat_id)
        if self.fired is not None:
            for chat in audience:
                if (last := self.fired.last(chat)) and last.job_id == job_id:
                    self.fired.forget(chat)
        now = self.clock()
        self._write_history(lambda history: history.mark_off(job_id, now, who))
        self._tell_others(chat_id, f"🔕 {who} apagó la alarma: «{ringing.message}»")
        return ringing.message

    def stop_all_ringing(self) -> int:
        """Corta las repeticiones de todas las alarmas que suenan, como el tope; devuelve cuántas."""
        if self.ringing is None:
            return 0
        return sum(
            self._stop_ringing(ringing.job_id) is not None for ringing in self.ringing.all()
        )

    def _audience(self, chat_id: int | None) -> list[int]:
        return self.chat_ids or ([chat_id] if chat_id is not None else [])

    def _tell_others(self, chat_id: int, text: str) -> None:
        """Escribe a todos los chats menos al que tocó el botón."""
        for chat in self._audience(chat_id):
            if chat != chat_id:
                self._write(chat, text)

    def _stop_ringing(self, job_id: int) -> Ringing | None:
        """Deja de repetir la alarma; devuelve lo que sonaba, o None si no sonaba."""
        self.timer.unschedule(_ring_key(job_id))
        if self.ringing is None:
            return None
        return self.ringing.take(job_id)

    def _arm_ring(self, job_id: int, when: datetime) -> None:
        self.timer.schedule(_ring_key(job_id), when, lambda: self._ring(job_id))

    def _next_ring(self, job_id: int, fired_at: datetime) -> None:
        """Agenda la repetición siguiente, sin pasar el tope; nada si ya la apagaron."""
        when = min(self.clock() + RING_DELAY, fired_at + RING_LIMIT)
        if self.ringing.set_next(job_id, when):
            self._arm_ring(job_id, when)

    def _ring(self, job_id: int) -> None:
        """Vuelve a hacer sonar una alarma que nadie apagó, o la cierra en el tope."""
        ringing = self.ringing.get(job_id)
        if ringing is None:
            return
        if self.clock() - ringing.fired_at >= RING_LIMIT:
            if self._stop_ringing(job_id) is not None:
                for chat in self._audience(ringing.chat_id):
                    self._write(chat, f"⏰ Dejé de sonar: «{ringing.message}», nadie la apagó")
            return

        rings = ringing.rings + 1
        self.ringing.mark_rang(job_id)
        self._write_history(lambda history: history.mark_nag(job_id))
        try:
            self.announce(_ringing_job(ringing), rings=rings, write=rings % RING_WRITE_EVERY == 0)
        except Exception:
            log.exception("could not ring job %s again", job_id)
        self._next_ring(job_id, ringing.fired_at)

    def _write(self, chat: int, text: str) -> None:
        """Escribe a un chat sin que una falla frene a los demás."""
        if self.notify is None:
            return
        try:
            self.notify(chat, text)
        except Exception:
            log.exception("could not tell chat %s", chat)

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

    def _take_dose(self, chat_id: int, stock_id: int) -> None:
        """Descuenta una dosis; al cruzar el umbral avisa y lo suma a compras."""
        if self.stock is None:
            return
        try:
            taken = self.stock.take_dose(stock_id)
            if taken is None:
                return
            supply, crossed = taken
            if not crossed:
                return
            for chat in self._audience(chat_id):
                self._write(chat, _running_out(supply))
            if self.lists is not None:
                self.lists.add(SHOPPING, [supply.name])
        except Exception:
            log.exception("could not take a dose from stock %s", stock_id)

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
        turn = turn_for(job, job.when)
        if turn is not None:
            job = replace(job, message=with_turn(job.message, turn))

        holiday = self._holiday(job)
        if holiday is not None:
            self._skip(job, holiday)
            self._move_on(job)
            return

        # Antes de anunciar: el botón de posponer llega con el aviso.
        if self.fired is not None:
            at = self.clock()
            for chat in self._audience(job.chat_id):
                self.fired.remember(
                    chat, job.message, job.device, at, job.kind, job.id, job.stock_id
                )
        if self.awaiting is not None and job.is_reminder:
            at = self.clock()
            next_nag = at + NAG_DELAY if self._nags() else None
            self.awaiting.remember(job.id, job.message, at, next_nag, job.stock_id)
            if next_nag is not None:
                self._arm_nag(job.id, job.chat_id, next_nag)
        fired_at = self.clock()
        rings = (
            self.ringing is not None
            and job.kind == ALARM
            and not away_of(self.quiet, fired_at)
        )
        if rings:
            self.ringing.remember(job.id, job.chat_id, job.message, job.device, fired_at)
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
        if rings:
            self._next_ring(job.id, fired_at)
        self._move_on(job)

    def _move_on(self, job: Job) -> None:
        """Reagenda el job a su ocurrencia siguiente, o lo borra si no repite."""
        next_time = next_run(job, job.when)
        if next_time is None:
            self.timer.unschedule(str(job.id))
            self.store.remove(job.id)
        else:
            self.store.reschedule(job.id, next_time)
            self._arm(self.store.get(job.id))

    def _holiday(self, job: Job) -> Holiday | None:
        """El feriado por el que el job no suena hoy; una caché rota deja que suene."""
        try:
            return skips(job, job.when.date(), self.holidays)
        except Exception:
            log.exception("could not read the holidays for job %s", job.id)
            return None

    def _skip(self, job: Job, holiday: Holiday) -> None:
        """Deja el feriado en el historial y avisa a todos los chats que hoy no suena."""
        at = self.clock()
        self._write_history(
            lambda history: history.record(
                job.id, job.chat_id, job.kind, job.repeat, job.message, at
            )
        )
        self._write_history(lambda history: history.mark_closed(job.id, HOLIDAY, at))
        log.info("job %s skipped: holiday %s", job.id, holiday.day)
        for chat in self._audience(job.chat_id):
            self._write(chat, f"🏖 Feriado ({holiday.name}): hoy no suena «{job.message}»")


def _running_out(supply: Stock) -> str:
    """El aviso de que se acaba un remedio."""
    if supply.count <= 0:
        return f"💊 No quedan de {supply.name}, comprar."
    return f"💊 Quedan {supply.count} de {supply.name}, comprar."


def _ring_key(job_id: int) -> str:
    """La clave del timer de la repetición, distinta de la del job y la del re-aviso."""
    return f"ring:{job_id}"


def _ringing_job(ringing: Ringing) -> Job:
    """La alarma que suena como job, aunque ya no esté en `jobs`."""
    return Job(
        id=ringing.job_id,
        chat_id=ringing.chat_id,
        when=ringing.fired_at,
        message=ringing.message,
        device=ringing.devices,
    )


def _nag_key(job_id: int) -> str:
    """La clave del timer del re-aviso, distinta de la del job."""
    return f"nag:{job_id}"

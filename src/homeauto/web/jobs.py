"""Crear, editar y borrar avisos y tachar ítems desde la pantalla, sin nada de HTTP."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, Iterable

from homeauto.bot.commands import format_when
from homeauto.lists import LISTS, split_items
from homeauto.people import display_name
from homeauto.schedule.month import item_kind
from homeauto.schedule.spec import SpecError, classify, resolve
from homeauto.schedule.store import DAILY, WEEKLY, Job
from homeauto.timespec import format_weekdays
from homeauto.web.board import KIND_ICONS

log = logging.getLogger(__name__)

MAX_MESSAGE = 500


class WebError(Exception):
    """Un pedido que no se puede atender; el texto es para la persona."""

    status = 400


class NotFound(WebError):
    status = 404


class ReadOnly(WebError):
    status = 403


def _in_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True).start()


def cancel_action(job_id: int) -> tuple[str, str]:
    """El botón que borra el aviso desde cualquier chat."""
    return (f"Cancelar #{job_id}", f"borrar {job_id}")


class JobsService:
    """Lo que la pantalla puede escribir: avisos de la casa e ítems de las listas."""

    def __init__(
        self,
        reminders,
        store,
        devices: Iterable[str],
        chat_ids: Iterable[int],
        people=None,
        lists=None,
        notify: Callable[..., None] | None = None,
        clock: Callable[[], datetime] = datetime.now,
        spawn: Callable[[Callable[[], None]], None] = _in_thread,
    ):
        self.reminders = reminders
        self.store = store
        self.devices = set(devices)
        self.chat_ids = sorted(chat_ids)
        self.people_store = people
        self.lists = lists
        self.notify = notify
        self.clock = clock
        self.spawn = spawn

    @property
    def writable(self) -> bool:
        return bool(self.chat_ids)

    def people(self) -> dict:
        """La gente de la casa para elegir el autor, los equipos y si se puede escribir."""
        names = self._names()
        return {
            "writable": self.writable,
            "people": [
                {"chat_id": chat_id, "name": display_name(chat_id, names)}
                for chat_id in self.chat_ids
            ],
            "devices": sorted(self.devices),
        }

    def job(self, job_id: int) -> dict:
        job = self.store.get(job_id)
        if job is None:
            raise NotFound(f"No existe el aviso #{job_id}.")
        return self._as_dict(job)

    def create(self, payload: dict) -> dict:
        self._check_writable()
        author = payload.get("author")
        if type(author) is not int or author not in self.chat_ids:
            raise WebError("Elegí a nombre de quién va el aviso.")
        fields = self._fields(payload)
        try:
            job = self.reminders.add(author, **fields)
        except ValueError as exc:
            raise WebError(str(exc)) from None
        name = display_name(author, self._names())
        self._tell(f"🖥️ {name} programó desde la pantalla {self._describe(job)}",
                   (cancel_action(job.id),))
        return self._as_dict(job)

    def update(self, job_id: int, payload: dict) -> dict:
        """Edita la serie entera; el autor no cambia."""
        self._check_writable()
        if self.store.get(job_id) is None:
            raise NotFound(f"No existe el aviso #{job_id}.")
        fields = self._fields(payload)
        try:
            job = self.reminders.update(job_id, **fields)
        except ValueError as exc:
            raise WebError(str(exc)) from None
        if job is None:
            raise NotFound(f"No existe el aviso #{job_id}.")
        self._tell(f"🖥️ Se cambió desde la pantalla {self._describe(job)}",
                   (cancel_action(job.id),))
        return self._as_dict(job)

    def delete(self, job_id: int) -> None:
        self._check_writable()
        job = self.store.get(job_id)
        if job is None or not self.reminders.cancel(None, job_id, any_owner=True):
            raise NotFound(f"No existe el aviso #{job_id}.")
        self._tell(f"🖥️ Se canceló desde la pantalla #{job.id}: «{job.message}»", ())

    def cross_out(self, list_name: str, item_id: int) -> str:
        """Saca un ítem de una lista por su id y devuelve su texto."""
        self._check_writable()
        if self.lists is None or list_name not in LISTS:
            raise NotFound("No existe esa lista.")
        removed = self.lists.remove_id(list_name, item_id)
        if removed is None:
            raise NotFound("Ese ítem ya no está en la lista.")
        return removed

    def add_items(self, list_name: str, text: object) -> dict:
        """Suma a una lista lo escrito, partido como en el chat. Devuelve lo agregado y lo repetido."""
        self._check_writable()
        if self.lists is None or list_name not in LISTS:
            raise NotFound("No existe esa lista.")
        if not isinstance(text, str):
            raise WebError("Falta qué agregar.")
        if len(text) > MAX_MESSAGE:
            raise WebError(f"No puede pasar de {MAX_MESSAGE} caracteres.")
        wanted = split_items(text)
        if not wanted:
            raise WebError("Falta qué agregar.")
        added = self.lists.add(list_name, wanted)
        return {"added": added, "repeated": [item for item in wanted if item not in added]}

    def _check_writable(self) -> None:
        if not self.writable:
            raise ReadOnly("La pantalla es de solo lectura: no hay chats de la casa configurados.")

    def _names(self) -> dict[int, str]:
        return self.people_store.names() if self.people_store is not None else {}

    def _fields(self, payload: dict) -> dict:
        """Lo que pide el formulario, validado y listo para el store."""
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise WebError("Falta el mensaje.")
        message = message.strip()
        if len(message) > MAX_MESSAGE:
            raise WebError(f"El mensaje no puede pasar de {MAX_MESSAGE} caracteres.")

        device = payload.get("device") or None
        if device is not None and device not in self.devices:
            raise WebError("No conozco ese equipo.")

        raw_days = payload.get("days") or []
        if not isinstance(raw_days, list) or any(type(day) is not int for day in raw_days):
            raise WebError("Los días tienen que ser una lista de números.")

        raw_when = payload.get("when")
        try:
            when = datetime.fromisoformat(raw_when) if isinstance(raw_when, str) else None
        except ValueError:
            when = None
        if when is None or when.tzinfo is not None:
            raise WebError("Falta la fecha y hora, en hora local.")

        try:
            kind, repeat = classify(payload.get("type"), payload.get("repeat"))
            days = tuple(raw_days) if repeat == WEEKLY else None
            when = resolve(repeat, when.replace(second=0, microsecond=0), self.clock(), days)
        except SpecError as exc:
            raise WebError(str(exc)) from None
        return {"when": when, "message": message, "repeat": repeat, "device": device,
                "days": days, "kind": kind}

    def _as_dict(self, job: Job) -> dict:
        return {
            "id": job.id,
            "type": item_kind(job.kind, job.repeat),
            "message": job.message,
            "when": job.when.strftime("%Y-%m-%dT%H:%M"),
            "repeat": job.repeat,
            "days": job.weekdays,
            "device": job.device or "",
            "author": job.chat_id,
            "author_name": display_name(job.chat_id, self._names()),
        }

    def _describe(self, job: Job) -> str:
        """El aviso en una línea de chat: ícono, número, cuándo, repetición y mensaje."""
        text = f"{KIND_ICONS[item_kind(job.kind, job.repeat)]} #{job.id} · "
        text += format_when(job.when, self.clock())
        if job.repeat == DAILY:
            text += " · todos los días"
        elif job.repeat == WEEKLY:
            text += f" · {format_weekdays(job.weekdays)}"
        if job.device:
            text += f" · {job.device}"
        return f"{text} — «{job.message}»"

    def _tell(self, text: str, actions: tuple[tuple[str, str], ...]) -> None:
        """Avisa a todos los chats en un hilo aparte; un chat que falla no frena a los otros."""
        if self.notify is None:
            return
        chats = list(self.chat_ids)

        def work() -> None:
            for chat in chats:
                try:
                    if actions:
                        self.notify(chat, text, actions)
                    else:
                        self.notify(chat, text)
                except Exception:  # noqa: BLE001
                    log.exception("could not tell chat %s about a change from the screen", chat)

        self.spawn(work)

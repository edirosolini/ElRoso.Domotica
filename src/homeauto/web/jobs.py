"""Crear, editar y borrar avisos y tachar ítems desde la pantalla, sin nada de HTTP."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, Iterable

from homeauto.bot.commands import format_when
from homeauto.lists import LISTS, split_items
from homeauto.people import Person, PersonError, PersonNotFound, display_name
from homeauto.schedule.month import item_kind
from homeauto.schedule.spec import (
    SpecError, check_skip_holidays, classify, repetition_label, resolve,
)
from homeauto.schedule.store import (
    ASSIGNEES, MONTHLY, NOBODY, PERSON, WEEKLY, Job, on_monthday,
)
from homeauto.web.board import KIND_ICONS, for_name, person_names

log = logging.getLogger(__name__)

MAX_MESSAGE = 500
# El chat de un aviso cuyo autor no tiene Telegram; ningún chat real es cero.
NO_CHAT = 0


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


def _person(person: Person) -> dict:
    return {"id": person.id, "name": person.name, "chat_id": person.chat_id}


def _monthday(when: datetime, previous: Job | None) -> int:
    """El día del mes de la fecha elegida, o el del mensual editado si la fecha es donde ese cae."""
    if previous is not None and previous.is_monthly and previous.monthday:
        if on_monthday(when.year, when.month, previous.monthday, when).day == when.day:
            return previous.monthday
    return when.day


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
        household=None,
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
        self.household = household

    @property
    def writable(self) -> bool:
        return bool(self.chat_ids)

    def people(self) -> dict:
        """La gente de la casa: los chats, el padrón, los equipos y si se puede escribir."""
        names = self._names()
        persons = self.household.list() if self.household is not None else []
        return {
            "writable": self.writable,
            "people": [
                {"chat_id": chat_id, "name": display_name(chat_id, names)}
                for chat_id in self.chat_ids
            ],
            "devices": sorted(self.devices),
            "persons": [_person(person) for person in persons],
            "chats": [{"chat_id": chat_id, "seen": names.get(chat_id)} for chat_id in self.chat_ids],
        }

    def add_person(self, payload: dict) -> dict:
        self._check_padron()
        return self._on_padron(lambda: self.household.add(payload.get("name"),
                                                          payload.get("chat_id")))

    def change_person(self, person_id: int, payload: dict) -> dict:
        """Cambia el nombre, el chat o los dos; `chat_id` en null es sin Telegram."""
        self._check_padron()
        changes = {key: payload[key] for key in ("name", "chat_id") if key in payload}
        if not changes:
            raise WebError("Mandá el nombre, el chat o los dos.")
        return self._on_padron(lambda: self.household.update(person_id, **changes))

    def remove_person(self, person_id: int) -> dict:
        self._check_padron()
        return self._on_padron(lambda: self.household.remove(person_id))

    def _check_padron(self) -> None:
        self._check_writable()
        if self.household is None:
            raise NotFound("No existe el padrón.")

    @staticmethod
    def _on_padron(change: Callable[[], Person]) -> dict:
        """Hace el cambio del padrón y traduce sus negativas a las de la pantalla."""
        try:
            return _person(change())
        except PersonNotFound as exc:
            raise NotFound(str(exc)) from None
        except PersonError as exc:
            raise WebError(str(exc)) from None

    def job(self, job_id: int) -> dict:
        job = self.store.get(job_id)
        if job is None:
            raise NotFound(f"No existe el aviso #{job_id}.")
        return self._as_dict(job)

    def create(self, payload: dict) -> dict:
        self._check_writable()
        chat_id, author_id = self._author(payload)
        fields = self._fields(payload)
        fields.update(self._assignee(payload) or {"assignee": NOBODY, "assignee_id": None})
        try:
            job = self.reminders.add(chat_id, author_id=author_id, **fields)
        except ValueError as exc:
            raise WebError(str(exc)) from None
        self._tell(f"🖥️ {self._author_name(job)} programó desde la pantalla {self._describe(job)}",
                   (cancel_action(job.id),))
        return self._as_dict(job)

    def update(self, job_id: int, payload: dict) -> dict:
        """Edita la serie entera; el autor no cambia."""
        self._check_writable()
        previous = self.store.get(job_id)
        if previous is None:
            raise NotFound(f"No existe el aviso #{job_id}.")
        fields = self._fields(payload, previous)
        fields.update(self._assignee(payload) or {})
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

    def _person(self, person_id: object) -> Person | None:
        if type(person_id) is not int or self.household is None:
            return None
        return self.household.get(person_id)

    def _author(self, payload: dict) -> tuple[int, int | None]:
        """El chat y la persona a cuyo nombre va el aviso: un chat de la casa o una del padrón."""
        chat_id, person_id = payload.get("author"), payload.get("author_id")
        if chat_id is not None and person_id is not None:
            raise WebError("Mandá el chat o la persona, no los dos.")
        if person_id is not None:
            person = self._person(person_id)
            if person is None:
                raise WebError("Elegí a nombre de quién va el aviso.")
            return (person.chat_id if person.chat_id is not None else NO_CHAT), person.id
        if type(chat_id) is not int or chat_id not in self.chat_ids:
            raise WebError("Elegí a nombre de quién va el aviso.")
        person = self.household.by_chat(chat_id) if self.household is not None else None
        return chat_id, person.id if person is not None else None

    def _assignee(self, payload: dict) -> dict | None:
        """Para quién es, validado contra el padrón; None si el pedido no lo dice."""
        if "assignee" not in payload:
            return None
        assignee, person_id = payload.get("assignee"), payload.get("assignee_id")
        if assignee not in ASSIGNEES:
            raise WebError("Elegí para quién es el aviso.")
        if assignee != PERSON:
            if person_id is not None:
                raise WebError("Solo un aviso para una persona lleva a quién.")
            return {"assignee": assignee, "assignee_id": None}
        if self._person(person_id) is None:
            raise WebError("No existe esa persona en la casa.")
        return {"assignee": assignee, "assignee_id": person_id}

    def _author_name(self, job: Job) -> str:
        """El nombre del autor: la persona del padrón, o el del chat como lo ve Telegram."""
        person = self._person(job.author_id)
        if person is None and job.chat_id != NO_CHAT and self.household is not None:
            person = self.household.by_chat(job.chat_id)
        return person.name if person is not None else display_name(job.chat_id, self._names())

    def _fields(self, payload: dict, previous: Job | None = None) -> dict:
        """Lo que pide el formulario, validado para el store; `previous` es el job editado."""
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

        skip_holidays = payload.get("skip_holidays", False)
        if type(skip_holidays) is not bool:
            raise WebError("«No suena en feriados» tiene que ser sí o no.")

        raw_when = payload.get("when")
        try:
            when = datetime.fromisoformat(raw_when) if isinstance(raw_when, str) else None
        except ValueError:
            when = None
        if when is None or when.tzinfo is not None:
            raise WebError("Falta la fecha y hora, en hora local.")

        try:
            kind, repeat = classify(payload.get("type"), payload.get("repeat"))
            check_skip_holidays(repeat, skip_holidays)
            days = tuple(raw_days) if repeat == WEEKLY else None
            monthday = _monthday(when, previous) if repeat == MONTHLY else None
            when = resolve(
                repeat, when.replace(second=0, microsecond=0), self.clock(), days, monthday
            )
        except SpecError as exc:
            raise WebError(str(exc)) from None
        return {"when": when, "message": message, "repeat": repeat, "device": device,
                "days": days, "kind": kind, "monthday": monthday,
                "skip_holidays": skip_holidays}

    def _as_dict(self, job: Job) -> dict:
        return {
            "id": job.id,
            "type": item_kind(job.kind, job.repeat),
            "message": job.message,
            "when": job.when.strftime("%Y-%m-%dT%H:%M"),
            "repeat": job.repeat,
            "days": job.weekdays,
            "monthday": job.monthday,
            "skip_holidays": job.skip_holidays,
            "device": job.device or "",
            "author": job.chat_id,
            "author_id": job.author_id,
            "author_name": self._author_name(job),
            "assignee": job.assignee,
            "assignee_id": job.assignee_id,
            "assignee_name": self._assignee_name(job),
        }

    def _assignee_name(self, job: Job) -> str | None:
        """El nombre de la persona del aviso; None si es de nadie, de todos o ya no está."""
        person = self._person(job.assignee_id) if job.assignee == PERSON else None
        return person.name if person is not None else None

    def _describe(self, job: Job) -> str:
        """El aviso en una línea de chat: ícono, número, cuándo, repetición y mensaje."""
        text = f"{KIND_ICONS[item_kind(job.kind, job.repeat)]} #{job.id} · "
        text += format_when(job.when, self.clock())
        repetition = repetition_label(job)
        if repetition:
            text += f" · {repetition}"
        if job.device:
            text += f" · {job.device}"
        whom = for_name(job.assignee, job.assignee_id, person_names(self.household))
        if whom:
            text += f" · para {whom}"
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

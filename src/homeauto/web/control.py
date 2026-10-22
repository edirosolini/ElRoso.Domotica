"""Manejar la casa desde la pantalla: lo urgente de ahora y los comandos, sin nada de HTTP."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Iterable

from homeauto.bot.commands import CHATLESS_BUTTONS, with_actions
from homeauto.people import display_name
from homeauto.schedule.awaiting import KEEP
from homeauto.schedule.reminders import SNOOZE_WINDOW
from homeauto.web.board import for_name, person_names
from homeauto.web.jobs import ReadOnly, WebError

log = logging.getLogger(__name__)

MAX_TEXT = 500

BROKEN = "🔴 No pude procesar la solicitud: {reason}"

OFF = ("🔕 Apagar", "callar {job}")
DONE = ("✅ Hecho", "hecho {job}")
SNOOZE = (("Posponer 10 min", "posponer 10m"), ("Posponer 30 min", "posponer 30m"))
CONFIRM = ("✅ Confirmar", "confirmar {name}")
HUSH = ("Silenciar 1 h", "silencio 1h")
TALK = ("Hablar ya", "hablar")
BACK = ("Cortar vacaciones", "vacaciones off")


def _actions(pairs: Iterable[tuple[str, str]]) -> list[dict]:
    return [{"label": label, "data": data} for label, data in pairs]


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


class ControlService:
    """Lo que la pantalla de control lee y ejecuta, a nombre de un chat de la casa."""

    def __init__(
        self,
        commands,
        ringing,
        awaiting,
        fired,
        monitor,
        quiet,
        people,
        alert_recipients: Iterable[int],
        chat_ids: Iterable[int],
        clock: Callable[[], datetime] = datetime.now,
        household=None,
    ):
        self.commands = commands
        self.ringing = ringing
        self.awaiting = awaiting
        self.fired = fired
        self.monitor = monitor
        self.quiet = quiet
        self.people = people
        self.alert_recipients = frozenset(alert_recipients)
        self.chat_ids = frozenset(chat_ids)
        self.clock = clock
        self.household = household

    def _caller(self, chat_id, person_id) -> tuple[int | None, str]:
        """El chat a cuyo nombre se corre, o None sin Telegram, y el nombre de quien pide."""
        if not self.chat_ids:
            raise ReadOnly("Sin ALLOWED_CHAT_IDS la pantalla no maneja la casa.")
        if person_id is not None:
            if chat_id is not None:
                raise WebError("Mandá chat_id o person_id, no los dos.")
            person = None
            if type(person_id) is int and self.household is not None:
                person = self.household.get(person_id)
            if person is None:
                raise ReadOnly("Elegí quién sos.")
            return person.chat_id, person.name
        if type(chat_id) is not int or chat_id not in self.chat_ids:
            raise ReadOnly("Elegí quién sos.")
        person = self.household.by_chat(chat_id) if self.household is not None else None
        if person is not None:
            return chat_id, person.name
        return chat_id, display_name(chat_id, self.people.names())

    def live(self, chat_id=None, person_id=None) -> dict:
        """Lo que pide atención ahora, con los botones que le tocan a ese chat o esa persona."""
        chat_id, _ = self._caller(chat_id, person_id)
        now = self.clock()
        return {
            "now": now.isoformat(),
            "ringing": self._ringing(),
            "awaiting": self._awaiting(now),
            "snooze": self._snooze(chat_id, now) if chat_id is not None else None,
            "outages": self._outages(chat_id),
            "quiet": self._quiet(now, chat_id is not None),
            "status": self._status(),
        }

    def _ringing(self) -> list[dict]:
        names = person_names(self.household)
        return [
            {
                "job_id": ring.job_id,
                "message": ring.message,
                "since": ring.fired_at.isoformat(),
                "rings": ring.rings,
                "for": for_name(ring.assignee, ring.assignee_id, names),
                "actions": _actions([(OFF[0], OFF[1].format(job=ring.job_id))]),
            }
            for ring in self.ringing.all()
        ]

    def _awaiting(self, now: datetime) -> list[dict]:
        names = person_names(self.household)
        return [
            {
                "job_id": wait.job_id,
                "message": wait.message,
                "since": wait.fired_at.isoformat(),
                "nags": wait.nags,
                "for": for_name(wait.assignee, wait.assignee_id, names),
                "actions": _actions([(DONE[0], DONE[1].format(job=wait.job_id))]),
            }
            for wait in self.awaiting.all()
            if now - wait.fired_at <= KEEP
        ]

    def _snooze(self, chat_id: int, now: datetime) -> dict | None:
        last = self.fired.last(chat_id)
        if last is None or now - last.at > SNOOZE_WINDOW:
            return None
        return {
            "job_id": last.job_id,
            "message": last.message,
            "kind": last.kind,
            "since": last.at.isoformat(),
            "for": for_name(last.assignee, last.assignee_id, person_names(self.household)),
            "actions": _actions(SNOOZE),
        }

    def _snapshot(self) -> dict:
        return self.monitor.snapshot() if self.monitor is not None else {}

    def _outages(self, chat_id: int | None) -> list[dict]:
        can_confirm = chat_id in self.alert_recipients
        return [
            {
                "name": state.name,
                "since": state.since.isoformat(),
                "actions": _actions(
                    [(CONFIRM[0], CONFIRM[1].format(name=state.name))] if can_confirm else []
                ),
            }
            for state in sorted(self._snapshot().values(), key=lambda state: state.name)
            if not state.up and state.alerted and not state.acked_by
        ]

    def _status(self) -> list[dict]:
        return [
            {"name": state.name, "up": state.up}
            for state in sorted(self._snapshot().values(), key=lambda state: state.name)
        ]

    def _quiet(self, now: datetime, can_act: bool = True) -> dict:
        until = getattr(self.quiet, "until", None)
        hush_until = until(now) if until is not None else None
        away_until = self.quiet.away_until(now)
        quiet = self.quiet.is_quiet(now)
        if away_until is not None:
            action = BACK
        elif hush_until is not None:
            action = TALK
        else:
            action = HUSH
        return {
            "quiet": quiet,
            "reason": self.quiet.reason(now) if quiet else "",
            "hush_until": _iso(hush_until),
            "away_until": _iso(away_until),
            "actions": _actions([action] if can_act else []),
        }

    def run(self, payload: dict) -> dict:
        """Corre un botón (`data`) o un mensaje suelto (`text`) y devuelve la respuesta con sus botones."""
        chat_id, name = self._caller(payload.get("chat_id"), payload.get("person_id"))
        data, text = payload.get("data"), payload.get("text")
        if (data is None) == (text is None):
            raise WebError("Mandá un comando o un texto.")
        value = data if data is not None else text
        if not isinstance(value, str) or not value.strip():
            raise WebError("Mandá un comando o un texto.")
        if len(value) > MAX_TEXT:
            raise WebError(f"El texto pasa de {MAX_TEXT} caracteres.")

        who = f"{name} (pantalla)"
        typed = self._typed(value) if text is not None and chat_id is not None else None
        if typed is not None:
            data = value = typed
        if chat_id is None and (data is None or value.split()[0] not in CHATLESS_BUTTONS):
            raise ReadOnly(
                f"{name} no tiene Telegram: desde la pantalla solo puede apagar una alarma"
                " o marcar «Hecho»."
            )
        try:
            if chat_id is None:
                reply = with_actions(self.commands.press_without_chat, value.strip(), who)
            elif data is not None:
                reply = with_actions(self.commands.press, chat_id, value.strip(), who)
            else:
                reply = with_actions(self.commands.free_text, chat_id, value.strip(), who=who)
        except Exception as exc:  # noqa: BLE001
            log.exception("el comando de la pantalla se rompió")
            return {"text": BROKEN.format(reason=exc), "actions": []}
        return {"text": reply.text, "actions": _actions(reply.actions)}

    def _typed(self, text: str) -> str | None:
        """El comando sin la barra si `text` escribe uno que se puede escribir, o None."""
        head, _, argument = text.strip().partition(" ")
        if not head.startswith("/"):
            return None
        command = head[1:].lower()
        if not self.commands.typed(command):
            return None
        return f"{command} {argument.strip()}".strip()

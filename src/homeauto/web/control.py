"""Manejar la casa desde la pantalla: lo urgente de ahora y los comandos, sin nada de HTTP."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Iterable

from homeauto.bot.commands import with_actions
from homeauto.people import display_name
from homeauto.schedule.awaiting import KEEP
from homeauto.schedule.reminders import SNOOZE_WINDOW
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

    def _check_chat(self, chat_id) -> int:
        """El chat, si es de la casa; si no, levanta ReadOnly."""
        if not self.chat_ids:
            raise ReadOnly("Sin ALLOWED_CHAT_IDS la pantalla no maneja la casa.")
        if type(chat_id) is not int or chat_id not in self.chat_ids:
            raise ReadOnly("Elegí quién sos.")
        return chat_id

    def live(self, chat_id) -> dict:
        """Lo que pide atención ahora, con los botones que le tocan a ese chat."""
        chat_id = self._check_chat(chat_id)
        now = self.clock()
        return {
            "now": now.isoformat(),
            "ringing": self._ringing(),
            "awaiting": self._awaiting(now),
            "snooze": self._snooze(chat_id, now),
            "outages": self._outages(chat_id),
            "quiet": self._quiet(now),
            "status": self._status(),
        }

    def _ringing(self) -> list[dict]:
        return [
            {
                "job_id": ring.job_id,
                "message": ring.message,
                "since": ring.fired_at.isoformat(),
                "rings": ring.rings,
                "actions": _actions([(OFF[0], OFF[1].format(job=ring.job_id))]),
            }
            for ring in self.ringing.all()
        ]

    def _awaiting(self, now: datetime) -> list[dict]:
        return [
            {
                "job_id": wait.job_id,
                "message": wait.message,
                "since": wait.fired_at.isoformat(),
                "nags": wait.nags,
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
            "actions": _actions(SNOOZE),
        }

    def _snapshot(self) -> dict:
        return self.monitor.snapshot() if self.monitor is not None else {}

    def _outages(self, chat_id: int) -> list[dict]:
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

    def _quiet(self, now: datetime) -> dict:
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
            "actions": _actions([action]),
        }

    def run(self, payload: dict) -> dict:
        """Corre un botón (`data`) o un mensaje suelto (`text`) y devuelve la respuesta con sus botones."""
        chat_id = self._check_chat(payload.get("chat_id"))
        data, text = payload.get("data"), payload.get("text")
        if (data is None) == (text is None):
            raise WebError("Mandá un comando o un texto.")
        value = data if data is not None else text
        if not isinstance(value, str) or not value.strip():
            raise WebError("Mandá un comando o un texto.")
        if len(value) > MAX_TEXT:
            raise WebError(f"El texto pasa de {MAX_TEXT} caracteres.")

        who = f"{display_name(chat_id, self.people.names())} (pantalla)"
        try:
            if data is not None:
                reply = with_actions(self.commands.press, chat_id, value.strip(), who)
            else:
                reply = with_actions(self.commands.free_text, chat_id, value.strip(), who=who)
        except Exception as exc:  # noqa: BLE001
            log.exception("el comando de la pantalla se rompió")
            return {"text": BROKEN.format(reason=exc), "actions": []}
        return {"text": reply.text, "actions": _actions(reply.actions)}

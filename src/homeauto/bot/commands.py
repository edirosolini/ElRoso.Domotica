"""Command logic, free of any Telegram plumbing.

Every method takes the chat id and the raw argument text, and returns the reply
to send back. Device failures become sentences, never tracebacks: the person on
the other side is holding a phone, not a log viewer.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from homeauto.config import Config
from homeauto.schedule.store import DAILY, ONCE
from homeauto.timespec import TimeSpecError, parse_schedule
from homeauto.voice.caster import CastError
from homeauto.voice.tts import TtsError

log = logging.getLogger(__name__)

DEVICE_ERRORS = (CastError, TtsError)

HELP = """Hola. Le hablo al parlante de casa.

/decir <texto> — lo dice ahora
/timer 10m sacá la pizza — avisa dentro de un rato
/alarma 7:30 arriba — avisa a esa hora
/alarma diaria 7:30 arriba — todos los días
/lista — lo que está programado
/cancelar <n> — cancela uno
/volumen <0-100> — cambia el volumen
/parar — corta lo que esté sonando
/donde — qué dispositivo estoy usando

La hora se escribe como quieras: 10m, 5min, 2h, 90s, 1h30m, 23:15, mañana 8:00.
Una hora que ya pasó se entiende como la de mañana."""


def format_when(when: datetime, now: datetime) -> str:
    """Human wording for a moment, close to how a person would say it."""
    days = (when.date() - now.date()).days
    clock = when.strftime("%H:%M")
    if days == 0:
        return f"hoy {clock}"
    if days == 1:
        return f"mañana {clock}"
    return f"{when.strftime('%d/%m')} {clock}"


class Commands:
    def __init__(
        self,
        config: Config,
        speaker,
        reminders=None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.config = config
        self.speaker = speaker
        self.reminders = reminders
        self.clock = clock

    def _denial(self, chat_id: int) -> str | None:
        """Returns the refusal to send, or None when the chat may proceed."""
        if self.config.is_allowed(chat_id):
            return None
        log.warning("chat %s rechazado", chat_id)
        return "No estás en la lista. Pedile al dueño que agregue tu ID: " + str(chat_id)

    def _enrollment_hint(self, chat_id: int) -> str:
        # While the whitelist is empty anyone can drive the speaker. Say so, and
        # hand over the id needed to close it.
        if not self.config.is_open_enrollment:
            return ""
        return (
            f"\n\n⚠️ El bot está abierto: cualquiera que lo encuentre puede usarlo."
            f"\nTu chat ID es {chat_id}. Ponelo en ALLOWED_CHAT_IDS y reiniciá el servicio."
        )

    def start(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial
        return HELP + self._enrollment_hint(chat_id)

    def say(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        text = text.strip()
        if not text:
            return "¿Qué querés que diga? Ej: /decir la cena está lista"

        try:
            self.speaker.say(text)
        except DEVICE_ERRORS as exc:
            log.exception("no se pudo decir '%s'", text)
            return f"No pude decirlo: {exc}"
        return f"Dicho: «{text}»" + self._enrollment_hint(chat_id)

    def volume(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            percent = int(text.strip())
        except ValueError:
            return "El volumen va como número de 0 a 100. Ej: /volumen 40"

        try:
            self.speaker.set_volume(percent)
        except DEVICE_ERRORS as exc:
            return f"No pude cambiar el volumen: {exc}"
        return f"Volumen en {percent}"

    def stop(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            self.speaker.stop()
        except DEVICE_ERRORS as exc:
            return f"No pude parar: {exc}"
        return "Cortado"

    def where(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            return f"Estoy hablando por: {self.speaker.device_name()}"
        except DEVICE_ERRORS as exc:
            return f"No encuentro el dispositivo: {exc}"

    # --- programados -------------------------------------------------------

    def _schedule(self, chat_id: int, text: str, repeat: str, label: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        now = self.clock()
        try:
            when, message = parse_schedule(text, now=now)
        except TimeSpecError as exc:
            return str(exc)

        job = self.reminders.add(chat_id, when, message, repeat=repeat)
        return f"{label} #{job.id} para {format_when(when, now)}: «{message}»"

    def timer(self, chat_id: int, text: str) -> str:
        return self._schedule(chat_id, text, ONCE, "Programado")

    def alarm(self, chat_id: int, text: str) -> str:
        head, _, rest = text.strip().partition(" ")
        if head.lower() in ("diaria", "diario", "daily"):
            return self._schedule(chat_id, rest, DAILY, "Alarma todos los días")
        return self._schedule(chat_id, text, ONCE, "Alarma")

    def list(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        jobs = self.reminders.list(chat_id)
        if not jobs:
            return "No hay nada programado"

        now = self.clock()
        lines = [
            f"#{job.id} · {format_when(job.when, now)}"
            f"{' · todos los días' if job.is_daily else ''} — {job.message}"
            for job in jobs
        ]
        return "\n".join(lines)

    def cancel(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            job_id = int(text.strip().lstrip("#"))
        except ValueError:
            return "Decime el número. Ej: /cancelar 3 (lo ves con /lista)"

        if not self.reminders.cancel(chat_id, job_id):
            return f"No encontré el recordatorio #{job_id}"
        return f"Cancelado #{job_id}"

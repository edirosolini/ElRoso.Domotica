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
from homeauto.voice.registry import UnknownDevice
from homeauto.voice.tts import TtsError

log = logging.getLogger(__name__)

DEVICE_ERRORS = (CastError, TtsError, UnknownDevice)
TARGET_WORD = "en"

HELP = """Hola. Manejo los equipos de casa.

/decir <texto> — lo dice ahora
/decir en tv <texto> — lo dice en ese equipo
/timer 10m sacá la pizza — avisa dentro de un rato
/alarma 7:30 arriba — avisa a esa hora
/alarma diaria 7:30 arriba — todos los días
/lista — lo que está programado
/cancelar <n> — cancela uno
/volumen <0-100> — cambia el volumen
/parar — corta lo que esté sonando
/equipos — qué equipos tengo y cuál está activo
/usar <equipo> — cambia el equipo por defecto

La hora se escribe como quieras: 10m, 5min, 2h, 90s, 1h30m, 23:15, mañana 8:00.
Una hora que ya pasó se entiende como la de mañana.
Cualquier comando acepta «en <equipo>» adelante para mandarlo a otro lado."""


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
        speakers,
        reminders=None,
        preferences=None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.config = config
        self.speakers = speakers
        self.reminders = reminders
        self.preferences = preferences
        self.clock = clock

    # --- permisos y destino ------------------------------------------------

    def _denial(self, chat_id: int) -> str | None:
        """Returns the refusal to send, or None when the chat may proceed."""
        if self.config.is_allowed(chat_id):
            return None
        log.warning("chat %s rechazado", chat_id)
        return "No estás en la lista. Pedile al dueño que agregue tu ID: " + str(chat_id)

    def _enrollment_hint(self, chat_id: int) -> str:
        # While the whitelist is empty anyone can drive the speakers. Say so, and
        # hand over the id needed to close it.
        if not self.config.is_open_enrollment:
            return ""
        return (
            f"\n\n⚠️ El bot está abierto: cualquiera que lo encuentre puede usarlo."
            f"\nTu chat ID es {chat_id}. Ponelo en ALLOWED_CHAT_IDS y reiniciá el servicio."
        )

    def _default_alias(self, chat_id: int) -> str:
        chosen = self.preferences.default_device(chat_id) if self.preferences else None
        if chosen and self.speakers.has(chosen):
            return chosen
        return self.config.default_device

    def _split_target(self, chat_id: int, text: str) -> tuple[str, str]:
        """Pull a leading «en <equipo>» off the text, if it names a real one.

        Only strips it when the word after «en» is a known device: otherwise
        `/decir en casa hace frío` would lose half the sentence.
        """
        text = text.strip()
        head, _, rest = text.partition(" ")
        if head.lower() == TARGET_WORD:
            alias, _, remainder = rest.strip().partition(" ")
            if alias and self.speakers.has(alias):
                return alias.strip().lower(), remainder.strip()
        return self._default_alias(chat_id), text

    # --- comandos ----------------------------------------------------------

    def start(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial
        return HELP + self._enrollment_hint(chat_id)

    def say(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        alias, message = self._split_target(chat_id, text)
        if not message:
            return "¿Qué querés que diga? Ej: /decir la cena está lista"

        try:
            self.speakers.get(alias).say(message)
        except DEVICE_ERRORS as exc:
            log.exception("no se pudo decir '%s' en %s", message, alias)
            return f"No pude decirlo en {alias}: {exc}"
        return f"Dicho en {alias}: «{message}»" + self._enrollment_hint(chat_id)

    def volume(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        alias, rest = self._split_target(chat_id, text)
        try:
            percent = int(rest.strip())
        except ValueError:
            return "El volumen va como número de 0 a 100. Ej: /volumen 40"

        try:
            self.speakers.get(alias).set_volume(percent)
        except DEVICE_ERRORS as exc:
            return f"No pude cambiar el volumen de {alias}: {exc}"
        return f"Volumen de {alias} en {percent}"

    def stop(self, chat_id: int, text: str = "") -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        alias, _ = self._split_target(chat_id, text)
        try:
            self.speakers.get(alias).stop()
        except DEVICE_ERRORS as exc:
            return f"No pude parar {alias}: {exc}"
        return f"Cortado en {alias}"

    def devices(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        active = self._default_alias(chat_id)
        lines = [f"{alias}{'  ◀ activo' if alias == active else ''}" for alias in self.speakers.aliases]
        return "Equipos:\n" + "\n".join(lines) + "\n\nCambialo con /usar <equipo>"

    # Kept so /donde keeps working; it is the same question.
    where = devices

    def use(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        alias = text.strip().lower()
        if not alias:
            return "Decime cuál. Ej: /usar tv (los ves con /equipos)"
        if not self.speakers.has(alias):
            known = ", ".join(self.speakers.aliases)
            return f"No conozco '{alias}'. Tengo: {known}"

        if self.preferences:
            self.preferences.set_default_device(chat_id, alias)
        return f"Listo, ahora uso {alias}"

    # --- programados -------------------------------------------------------

    def _schedule(self, chat_id: int, text: str, repeat: str, label: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        alias, rest = self._split_target(chat_id, text)
        now = self.clock()
        try:
            when, message = parse_schedule(rest, now=now)
        except TimeSpecError as exc:
            return str(exc)

        job = self.reminders.add(chat_id, when, message, repeat=repeat, device=alias)
        return f"{label} #{job.id} en {alias} para {format_when(when, now)}: «{message}»"

    def timer(self, chat_id: int, text: str) -> str:
        return self._schedule(chat_id, text, ONCE, "Programado")

    def alarm(self, chat_id: int, text: str) -> str:
        alias, rest = self._split_target(chat_id, text)
        head, _, tail = rest.strip().partition(" ")
        prefix = f"{TARGET_WORD} {alias} " if alias != self._default_alias(chat_id) else ""
        if head.lower() in ("diaria", "diario", "daily"):
            return self._schedule(chat_id, prefix + tail, DAILY, "Alarma todos los días")
        return self._schedule(chat_id, prefix + rest, ONCE, "Alarma")

    def list(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        jobs = self.reminders.list(chat_id)
        if not jobs:
            return "No hay nada programado"

        now = self.clock()
        lines = [
            f"#{job.id} · {format_when(job.when, now)} · {job.device or self.config.default_device}"
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

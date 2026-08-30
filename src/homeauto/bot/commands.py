"""Command logic, free of any Telegram plumbing.

Every method takes the chat id and the raw argument text, and returns the reply
to send back. Device failures become sentences, never tracebacks: the person on
the other side is holding a phone, not a log viewer.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
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
ALL_WORD = "todos"

# A leading run of aliases: "comedor", "comedor,recamara", "comedor, recamara".
_TARGET_LIST = re.compile(r"^([a-z0-9_-]+(?:\s*,\s*[a-z0-9_-]+)*)(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)


class TargetError(Exception):
    """The devices asked for do not all exist."""

HELP = """Hola. Manejo los equipos de casa.

/decir <texto> — lo dice ahora
/decir en comedor <texto> — lo dice en ese equipo
/decir en comedor,recamara <texto> — en varios
/decir en todos <texto> — en toda la casa
/timer 10m sacá la pizza — avisa dentro de un rato
/alarma 7:30 arriba — avisa a esa hora
/alarma diaria 7:30 arriba — todos los días
/lista — lo que está programado
/cancelar <n> — cancela uno
/volumen <0-100> — cambia el volumen
/parar — corta lo que esté sonando
/apagar — cierra la app y deja el equipo en reposo
/equipos — qué equipos tengo y cuál está activo
/usar <equipo> — cambia el equipo por defecto (acepta varios y «todos»)

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

    def _default_aliases(self, chat_id: int) -> list[str]:
        stored = self.preferences.default_device(chat_id) if self.preferences else None
        chosen = [a for a in (stored or "").split(",") if a and self.speakers.has(a)]
        return chosen or [self.config.default_device]

    def _parse_aliases(self, spec: str) -> list[str] | None:
        """The aliases in «en <spec>», or None when it is not a target at all."""
        if spec.lower() == ALL_WORD:
            return list(self.speakers.aliases)

        parts = [part.strip().lower() for part in spec.split(",")]
        parts = [part for part in parts if part]
        if not parts:
            return None

        unknown = [part for part in parts if not self.speakers.has(part)]
        if not unknown:
            return list(dict.fromkeys(parts))  # dedup, keeping the order typed
        if len(parts) > 1:
            # A comma-separated list is unambiguously a target: say what is wrong
            # instead of quietly speaking half of it as if it were the message.
            raise TargetError(
                f"No conozco: {', '.join(unknown)}. Tengo: {', '.join(self.speakers.aliases)}"
            )
        # A single unknown word is just the message: "/decir en casa hace frío".
        return None

    def _split_target(self, chat_id: int, text: str) -> tuple[list[str], str]:
        """Pull a leading «en <equipos>» off the text, if it names real ones."""
        text = text.strip()
        head, _, rest = text.partition(" ")
        if head.lower() == TARGET_WORD:
            match = _TARGET_LIST.match(rest.strip())
            if match:
                aliases = self._parse_aliases(match.group(1))
                if aliases:
                    return aliases, (match.group(2) or "").strip()
        return self._default_aliases(chat_id), text

    def _broadcast(self, aliases: list[str], action) -> dict[str, str | None]:
        """Run the action on every device at once.

        In parallel on purpose: one after another, the same phrase starts a
        couple of seconds apart in each room and the house echoes.
        """
        def run(alias: str) -> str | None:
            try:
                action(self.speakers.get(alias))
                return None
            except DEVICE_ERRORS as exc:
                log.warning("falló %s: %s", alias, exc)
                return str(exc)

        with ThreadPoolExecutor(max_workers=len(aliases)) as pool:
            return dict(zip(aliases, pool.map(run, aliases)))

    @staticmethod
    def _summary(results: dict[str, str | None], done: str, failed: str) -> str:
        ok = [alias for alias, problem in results.items() if problem is None]
        bad = [f"{alias}: {problem}" for alias, problem in results.items() if problem]
        if not ok:
            return f"{failed}\n" + "\n".join(bad)
        text = f"{done} en {', '.join(ok)}"
        if bad:
            text += "\n\nNo pude en:\n" + "\n".join(bad)
        return text

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

        try:
            aliases, message = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        if not message:
            return "¿Qué querés que diga? Ej: /decir la cena está lista"

        results = self._broadcast(aliases, lambda speaker: speaker.say(message))
        summary = self._summary(results, "Dicho", "No pude decirlo en ninguno:")
        if all(problem is None for problem in results.values()):
            summary += f": «{message}»"
        return summary + self._enrollment_hint(chat_id)

    def volume(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            aliases, rest = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        try:
            percent = int(rest.strip())
        except ValueError:
            return "El volumen va como número de 0 a 100. Ej: /volumen 40"

        results = self._broadcast(aliases, lambda speaker: speaker.set_volume(percent))
        return self._summary(results, f"Volumen en {percent}", "No pude cambiar el volumen:")

    def stop(self, chat_id: int, text: str = "") -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            aliases, _ = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        results = self._broadcast(aliases, lambda speaker: speaker.stop())
        return self._summary(results, "Cortado", "No pude parar:")

    def turn_off(self, chat_id: int, text: str = "") -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            aliases, _ = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        results = self._broadcast(aliases, lambda speaker: speaker.turn_off())
        summary = self._summary(results, "Apagado", "No pude apagar:")
        if any(problem is None for problem in results.values()):
            summary += "\n\nEl televisor se apaga solo si lo tenés configurado para hacerlo al perder señal."
        return summary

    def devices(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        active = self._default_aliases(chat_id)
        lines = [
            f"{alias}{'  ◀ activo' if alias in active else ''}"
            for alias in self.speakers.aliases
        ]
        return (
            "Equipos:\n" + "\n".join(lines)
            + "\n\nCambialo con /usar <equipo>, o /usar todos."
            + "\nTambién podés mandar uno suelto: /decir en comedor,recamara hola"
        )

    # Kept so /donde keeps working; it is the same question.
    where = devices

    def use(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        spec = text.strip().lower()
        if not spec:
            return "Decime cuál. Ej: /usar comedor (los ves con /equipos)"

        try:
            aliases = self._parse_aliases(spec)
        except TargetError as exc:
            return str(exc)
        if not aliases:
            known = ", ".join(self.speakers.aliases)
            return f"No conozco '{spec}'. Tengo: {known}"

        if self.preferences:
            self.preferences.set_default_device(chat_id, ",".join(aliases))
        return f"Listo, ahora uso {', '.join(aliases)}"

    # --- programados -------------------------------------------------------

    def _schedule(self, chat_id: int, text: str, repeat: str, label: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            aliases, rest = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        now = self.clock()
        try:
            when, message = parse_schedule(rest, now=now)
        except TimeSpecError as exc:
            return str(exc)

        job = self.reminders.add(chat_id, when, message, repeat=repeat, device=",".join(aliases))
        return (
            f"{label} #{job.id} en {', '.join(aliases)} "
            f"para {format_when(when, now)}: «{message}»"
        )

    def timer(self, chat_id: int, text: str) -> str:
        return self._schedule(chat_id, text, ONCE, "Programado")

    def alarm(self, chat_id: int, text: str) -> str:
        try:
            aliases, rest = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        head, _, tail = rest.strip().partition(" ")
        prefix = f"{TARGET_WORD} {','.join(aliases)} "
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
            f"#{job.id} · {format_when(job.when, now)} · {', '.join(job.devices) or self.config.default_device}"
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

"""Qué pasa cuando dispara un timer, una alarma o un recordatorio.

Dos cosas independientes: el parlante lo dice y al chat le llega un mensaje. Si
no estás en casa el parlante no sirve, y si el parlante está apagado igual
querés que suene el teléfono.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Callable, Iterable

from homeauto.polish import as_is
from homeauto.quiet import away_of, reason_of
from homeauto.schedule.rota import turn_in, with_turn
from homeauto.schedule.spec import ringing_label
from homeauto.schedule.store import Job
from homeauto.voice import chime
from homeauto.voice.caster import CastError
from homeauto.voice.registry import UnknownDevice
from homeauto.voice.speaker import ALARM_MIN_VOLUME
from homeauto.voice.tts import TtsError

log = logging.getLogger(__name__)

DEVICE_ERRORS = (CastError, TtsError, UnknownDevice)

_CALLED = re.compile(r"\[([^\W\d_]+(?: [^\W\d_]+)*)\]\s*")


class Announcer:
    def __init__(
        self,
        speakers,
        notify: Callable[[int, str], None],
        fallback: str,
        quiet=None,
        clock: Callable[[], datetime] = datetime.now,
        polish: Callable[..., str] = as_is,
        actions: tuple[tuple[str, str], ...] = (),
        chat_ids: Iterable[int] = (),
        reminder_actions: tuple[tuple[str, str], ...] = (),
        ring_actions: tuple[tuple[str, str], ...] = (),
    ):
        self.speakers = speakers
        self.notify = notify
        # Un job agendado antes de que existieran los equipos no trae destino.
        self.fallback = fallback
        self.quiet = quiet
        self.clock = clock
        self.polish = polish
        # Botones del aviso: (etiqueta, comando con su argumento).
        self.actions = actions
        # Los de un recordatorio; `{job}` se reemplaza por su número.
        self.reminder_actions = reminder_actions
        # Los de una alarma que sigue sonando.
        self.ring_actions = ring_actions
        # Los chats que reciben el aviso; vacío es solo el que lo pidió.
        self.chat_ids = list(chat_ids)

    def __call__(self, job: Job, rings: int = 0) -> None:
        """Dice el job y lo escribe; `rings` es la repetición."""
        problem = None
        resting = self.quiet is not None and self.quiet.is_quiet(self.clock())
        turn = turn_in(job.message)
        called, name = _called(job.message, turn, job.addressee)
        message = self.polish(called, must_keep=tuple(word for word in (turn, name) if word))

        if resting:
            log.info("job %s cae en horario de descanso: solo va al chat", job.id)
        else:
            problems = []
            for alias in job.devices or [self.fallback]:
                try:
                    self.speakers.get(alias).say(
                        message, chime=self._sound(job, rings), min_volume=self._floor(job)
                    )
                except DEVICE_ERRORS as exc:
                    problems.append(f"{alias}: {exc}")
                    log.warning("el job %s no sonó en %s: %s", job.id, alias, exc)
            problem = "; ".join(problems) if problems else None

        if rings:
            text = self._ringing_text(job, problem, resting)
            actions = _numbered(self.ring_actions, job)
        else:
            text = self._text(message, job, problem, resting)
            actions = self._actions(job)
            if away_of(self.quiet, self.clock()):
                # En vacaciones saca los botones de apagar la alarma.
                off = _numbered(self.ring_actions, job)
                actions = tuple(action for action in actions if action not in off)
        for chat_id in self._chats(job):
            try:
                if actions:
                    self.notify(chat_id, text, actions)
                else:
                    self.notify(chat_id, text)
            except Exception:
                # El parlante puede ya haber hablado; un chat roto no deshace eso.
                log.exception("no se pudo avisar al chat %s del job %s", chat_id, job.id)

    def nag(self, job: Job) -> None:
        """Dice el re-aviso del job en sus equipos, sin pulir; en descanso o vacaciones calla."""
        if self.quiet is not None and self.quiet.is_quiet(self.clock()):
            log.info("el re-aviso del job %s cae en horario de descanso: no se dice", job.id)
            return
        text = _nag_line(job.message, job.addressee)
        for alias in job.devices or [self.fallback]:
            try:
                self.speakers.get(alias).say(
                    text, chime=self._sound(job), min_volume=self._floor(job)
                )
            except DEVICE_ERRORS as exc:
                log.warning("el re-aviso del job %s no sonó en %s: %s", job.id, alias, exc)

    def stop(self, devices: Iterable[str]) -> None:
        """Corta lo que esté sonando en esos equipos, o en el de siempre."""
        for alias in list(devices) or [self.fallback]:
            try:
                self.speakers.get(alias).stop()
            except Exception:
                log.exception("could not stop %s", alias)

    def _chats(self, job: Job) -> list[int]:
        """Los chats del job; sin audiencia propia, todos los de la casa o el que lo pidió."""
        if job.audience is not None:
            return list(job.audience)
        return self.chat_ids or [job.chat_id]

    @staticmethod
    def _sound(job: Job, rings: int = 0) -> str:
        if job.is_reminder:
            return chime.SOFT
        return chime.WAKE_LEVELS[min(rings, len(chime.WAKE_LEVELS) - 1)]

    @staticmethod
    def _floor(job: Job) -> int | None:
        """El piso de volumen del job; `None` deja el del equipo."""
        return None if job.is_reminder else ALARM_MIN_VOLUME

    def _actions(self, job: Job) -> tuple[tuple[str, str], ...]:
        if not job.is_reminder:
            return _numbered(self.actions, job)
        return _numbered(self.reminder_actions, job) or _numbered(self.actions, job)

    def _ringing_text(self, job: Job, problem: str | None, resting: bool) -> str:
        return self._tail(f"⏰ Sigue sonando: «{job.message}»", problem, resting)

    def _text(self, message: str, job: Job, problem: str | None, resting: bool = False) -> str:
        icon, noun = ("🔔", "recordatorio") if job.is_reminder else ("⏰", "alarma")
        text = f"{icon} {message}"
        repetition = ringing_label(job)
        if repetition:
            text += f"\n({noun} {repetition})"
        return self._tail(text, problem, resting)

    def _tail(self, text: str, problem: str | None, resting: bool) -> str:
        """Suma al texto por qué no se dijo en voz alta, si no se dijo."""
        if resting:
            text += f"\n\n{reason_of(self.quiet, self.clock())}: no lo dije en voz alta."
        elif problem:
            text += f"\n\nNo pude decirlo en voz alta: {problem}"
        return text


def _called(
    message: str, turn: str | None, addressee: str | None = None
) -> tuple[str, str | None]:
    """El mensaje dicho como llamado y a quién llama.

    Gana el «[Nombre]» tras el turno; sin corchete ni turno, llama a `addressee`.
    """
    prefix = with_turn("", turn) if turn else ""
    match = _CALLED.match(message, len(prefix))
    if match:
        name, rest = match.group(1), message[match.end():]
        return (f"{prefix}{name}, {rest}" if rest else f"{prefix}{name}"), name
    if addressee and not turn:
        return f"{addressee}, {message}", addressee
    return message, None


def nag_call(message: str, addressee: str | None = None) -> tuple[str | None, str]:
    """A quién llama el re-aviso y qué queda del mensaje: turno, «[Nombre]» o `addressee`, en ese orden."""
    turn = turn_in(message)
    if turn:
        return turn, _called(message[len(with_turn("", turn)):], None)[0]
    if match := _CALLED.match(message):
        return match.group(1), message[match.end():]
    return addressee, message


def _nag_line(message: str, addressee: str | None = None) -> str:
    """El re-aviso hablado: «<Nombre>, sigue pendiente: <mensaje>.»."""
    name, rest = nag_call(message, addressee)
    line = f"{name}, sigue pendiente" if name else "Sigue pendiente"
    if rest:
        line += f": {rest}"
    return line if line.endswith((".", "!", "?", "…")) else f"{line}."


def _numbered(actions: tuple[tuple[str, str], ...], job: Job) -> tuple[tuple[str, str], ...]:
    """Los botones con `{job}` reemplazado por el número del job."""
    return tuple((label, data.format(job=job.id)) for label, data in actions)

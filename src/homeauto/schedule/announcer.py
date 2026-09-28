"""Qué pasa cuando dispara un timer, una alarma o un recordatorio.

Dos cosas independientes: el parlante lo dice y al chat le llega un mensaje. Si
no estás en casa el parlante no sirve, y si el parlante está apagado igual
querés que suene el teléfono.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Iterable

from homeauto.polish import as_is
from homeauto.schedule.store import Job
from homeauto.timespec import format_weekdays
from homeauto.voice import chime
from homeauto.voice.caster import CastError
from homeauto.voice.registry import UnknownDevice
from homeauto.voice.tts import TtsError

log = logging.getLogger(__name__)

DEVICE_ERRORS = (CastError, TtsError, UnknownDevice)


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
        # Los chats que reciben el aviso; vacío es solo el que lo pidió.
        self.chat_ids = list(chat_ids)

    def __call__(self, job: Job) -> None:
        problem = None
        resting = self.quiet is not None and self.quiet.is_quiet(self.clock())
        message = self.polish(job.message)

        if resting:
            log.info("job %s cae en horario de descanso: solo va al chat", job.id)
        else:
            problems = []
            for alias in job.devices or [self.fallback]:
                try:
                    self.speakers.get(alias).say(message, chime=self._sound(job))
                except DEVICE_ERRORS as exc:
                    problems.append(f"{alias}: {exc}")
                    log.warning("el job %s no sonó en %s: %s", job.id, alias, exc)
            problem = "; ".join(problems) if problems else None

        text = self._text(message, job, problem, resting)
        actions = self._actions(job)
        for chat_id in self.chat_ids or [job.chat_id]:
            try:
                if actions:
                    self.notify(chat_id, text, actions)
                else:
                    self.notify(chat_id, text)
            except Exception:
                # El parlante puede ya haber hablado; un chat roto no deshace eso.
                log.exception("no se pudo avisar al chat %s del job %s", chat_id, job.id)

    @staticmethod
    def _sound(job: Job) -> str:
        return chime.SOFT if job.is_reminder else chime.ALARM

    def _actions(self, job: Job) -> tuple[tuple[str, str], ...]:
        if not job.is_reminder:
            return self.actions
        return tuple(
            (label, data.format(job=job.id)) for label, data in self.reminder_actions
        ) or self.actions

    def _text(self, message: str, job: Job, problem: str | None, resting: bool = False) -> str:
        icon, noun = ("🔔", "recordatorio") if job.is_reminder else ("⏰", "alarma")
        text = f"{icon} {message}"
        if job.is_daily:
            text += f"\n({noun} de todos los días)"
        elif job.is_weekly:
            text += f"\n({noun} de {format_weekdays(job.weekdays)})"
        if resting:
            text += f"\n\nHorario de descanso ({self.quiet.label}): no lo dije en voz alta."
        elif problem:
            text += f"\n\nNo pude decirlo en voz alta: {problem}"
        return text

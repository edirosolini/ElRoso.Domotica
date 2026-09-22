"""Qué pasa cuando dispara un timer o una alarma.

Dos cosas independientes: el parlante lo dice y al chat le llega un mensaje. Si
no estás en casa el parlante no sirve, y si el parlante está apagado igual
querés que suene el teléfono.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from homeauto.polish import as_is
from homeauto.schedule.store import Job
from homeauto.timespec import format_weekdays
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
    ):
        self.speakers = speakers
        self.notify = notify
        # Un job agendado antes de que existieran los equipos no trae destino.
        self.fallback = fallback
        self.quiet = quiet
        self.clock = clock
        self.polish = polish

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
                    self.speakers.get(alias).say(message, chime=True)
                except DEVICE_ERRORS as exc:
                    problems.append(f"{alias}: {exc}")
                    log.warning("el job %s no sonó en %s: %s", job.id, alias, exc)
            problem = "; ".join(problems) if problems else None

        try:
            self.notify(job.chat_id, self._text(message, job, problem, resting))
        except Exception:
            # El parlante puede ya haber hablado; un chat roto no deshace eso.
            log.exception("no se pudo avisar por chat del job %s", job.id)

    def _text(self, message: str, job: Job, problem: str | None, resting: bool = False) -> str:
        text = f"⏰ {message}"
        if job.is_daily:
            text += "\n(alarma de todos los días)"
        elif job.is_weekly:
            text += f"\n(alarma de {format_weekdays(job.weekdays)})"
        if resting:
            text += f"\n\nHorario de descanso ({self.quiet.label}): no lo dije en voz alta."
        elif problem:
            text += f"\n\nNo pude decirlo en voz alta: {problem}"
        return text

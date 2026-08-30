"""What actually happens when a timer or an alarm fires.

Two independent things: the speaker says it, and the chat gets a message. They
are independent on purpose — if you are not home the speaker is useless, and if
the speaker is off you still want the phone to buzz.
"""

from __future__ import annotations

import logging
from typing import Callable

from homeauto.schedule.store import Job
from homeauto.voice.caster import CastError
from homeauto.voice.registry import UnknownDevice
from homeauto.voice.tts import TtsError

log = logging.getLogger(__name__)

DEVICE_ERRORS = (CastError, TtsError, UnknownDevice)


class Announcer:
    def __init__(self, speakers, notify: Callable[[int, str], None], fallback: str):
        self.speakers = speakers
        self.notify = notify
        # A job scheduled before the devices existed carries no target.
        self.fallback = fallback

    def __call__(self, job: Job) -> None:
        problem = None
        try:
            self.speakers.get(job.device or self.fallback).say(job.message)
        except DEVICE_ERRORS as exc:
            problem = str(exc)
            log.warning("el job %s no sonó: %s", job.id, problem)

        try:
            self.notify(job.chat_id, self._text(job, problem))
        except Exception:
            # The speaker may already have spoken; a broken chat does not undo that.
            log.exception("no se pudo avisar por chat del job %s", job.id)

    def _text(self, job: Job, problem: str | None) -> str:
        text = f"⏰ {job.message}"
        if job.is_daily:
            text += "\n(alarma de todos los días)"
        if problem:
            text += f"\n\nNo pude decirlo en voz alta: {problem}"
        return text

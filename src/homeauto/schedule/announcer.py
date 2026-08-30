"""What actually happens when a timer or an alarm fires.

Two independent things: the speaker says it, and the chat gets a message. They
are independent on purpose — if you are not home the speaker is useless, and if
the speaker is off you still want the phone to buzz.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from homeauto.schedule.store import Job
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
    ):
        self.speakers = speakers
        self.notify = notify
        # A job scheduled before the devices existed carries no target.
        self.fallback = fallback
        self.quiet = quiet
        self.clock = clock

    def __call__(self, job: Job) -> None:
        problem = None
        resting = self.quiet is not None and self.quiet.is_quiet(self.clock())

        if resting:
            log.info("job %s cae en horario de descanso: solo va al chat", job.id)
        else:
            problems = []
            for alias in job.devices or [self.fallback]:
                try:
                    self.speakers.get(alias).say(job.message)
                except DEVICE_ERRORS as exc:
                    problems.append(f"{alias}: {exc}")
                    log.warning("el job %s no sonó en %s: %s", job.id, alias, exc)
            problem = "; ".join(problems) if problems else None

        try:
            self.notify(job.chat_id, self._text(job, problem, resting))
        except Exception:
            # The speaker may already have spoken; a broken chat does not undo that.
            log.exception("no se pudo avisar por chat del job %s", job.id)

    def _text(self, job: Job, problem: str | None, resting: bool = False) -> str:
        text = f"⏰ {job.message}"
        if job.is_daily:
            text += "\n(alarma de todos los días)"
        if resting:
            text += f"\n\nHorario de descanso ({self.quiet.label}): no lo dije en voz alta."
        elif problem:
            text += f"\n\nNo pude decirlo en voz alta: {problem}"
        return text

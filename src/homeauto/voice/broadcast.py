"""Announcing something to the house, wherever the request came from.

The rules are the same for a Telegram command, an HTTP call or a calendar
event, so they live here once: which devices, whether the house is resting,
and the written copy that always reaches the chat.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Iterable

log = logging.getLogger(__name__)

# An urgent warning is worth turning the volume up for. The house gets its own
# level back as soon as the announcement ends.
URGENT_MIN_VOLUME = 60


class HouseVoice:
    def __init__(
        self,
        speakers,
        default_devices: list[str],
        notify: Callable[[int, str], None],
        chat_ids: Iterable[int],
        quiet=None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.speakers = speakers
        self.default_devices = list(default_devices)
        self.notify = notify
        self.chat_ids = list(chat_ids)
        self.quiet = quiet
        self.clock = clock

    def resting(self) -> bool:
        return self.quiet is not None and self.quiet.is_quiet(self.clock())

    def announce(
        self,
        text: str,
        devices: list[str] | None = None,
        urgent: bool = False,
        written: str | None = None,
    ) -> dict:
        """`written` is the chat copy when it carries more than what is said.

        A monitor alert quotes an HTTP status and a stack trace: useful to read,
        unlistenable, and full of digits that Piper reads wrong.
        """
        targets = list(devices or self.default_devices)

        # Urgent wins over the quiet window: production falling over at 3 AM is
        # exactly what somebody should be woken up for.
        if self.resting() and not urgent:
            log.info("aviso en horario de descanso: solo va al chat")
            self.tell_everyone(
                f"🔔 {written or text}\n\n(horario de descanso: no se dijo en voz alta)"
            )
            return {"spoken": False, "notified": True, "devices": targets, "problems": []}

        problems = []
        for alias in targets:
            try:
                self.speakers.get(alias).say(
                    text, min_volume=URGENT_MIN_VOLUME if urgent else None
                )
            except Exception as exc:  # noqa: BLE001 - se reporta al llamador
                log.warning("no pude hablar en %s: %s", alias, exc)
                problems.append(f"{alias}: {exc}")

        return {
            "spoken": len(problems) < len(targets),
            "notified": False,
            "devices": targets,
            "problems": problems,
        }

    def tell_everyone(self, text: str) -> None:
        for chat_id in self.chat_ids:
            try:
                self.notify(chat_id, text)
            except Exception:
                log.exception("no se pudo avisar al chat %s", chat_id)

"""Parsing of the human time specs accepted by the bot commands.

Accepted shapes, always followed by the message:

    10m sacá la pizza      relative duration (h / m / min / s, combinable)
    1h30m avisar
    23:15 apagá el horno   clock time, rolls to tomorrow if already passed
    mañana 8:00 dentista   explicit tomorrow
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

TOMORROW_WORDS = {"mañana", "manana"}

_CLOCK_RE = re.compile(r"(\d{1,2}):(\d{2})")
_DURATION_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)min|(\d+)m)?(?:(\d+)s)?", re.IGNORECASE)


class TimeSpecError(ValueError):
    """The text does not describe a moment we know how to schedule."""


def _split_head(text: str) -> tuple[str, str]:
    parts = text.split(None, 1)
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""


def _parse_duration(token: str) -> timedelta:
    match = _DURATION_RE.fullmatch(token)
    if match is None or not any(match.groups()):
        raise TimeSpecError(f"No entiendo cuándo: '{token}'")

    hours, minutes_long, minutes_short, seconds = match.groups()
    delta = timedelta(
        hours=int(hours or 0),
        minutes=int(minutes_long or minutes_short or 0),
        seconds=int(seconds or 0),
    )
    if delta <= timedelta(0):
        raise TimeSpecError("La duración tiene que ser mayor a cero")
    return delta


def _parse_clock(token: str, now: datetime, *, force_tomorrow: bool) -> datetime:
    match = _CLOCK_RE.fullmatch(token)
    if match is None:
        raise TimeSpecError(f"No entiendo la hora: '{token}'")

    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise TimeSpecError(f"No entiendo la hora: '{token}'")

    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # A clock time that already went by today means the next one, tomorrow.
    if force_tomorrow or when <= now:
        when += timedelta(days=1)
    return when


def parse_schedule(text: str, now: datetime) -> tuple[datetime, str]:
    """Return when to fire and what to say, or raise TimeSpecError."""
    head, rest = _split_head(text.strip())
    if not head:
        raise TimeSpecError("Falta la hora y el mensaje")

    if head.lower() in TOMORROW_WORDS:
        clock, rest = _split_head(rest)
        if not clock:
            raise TimeSpecError("Falta la hora después de 'mañana'")
        when = _parse_clock(clock, now, force_tomorrow=True)
    elif _CLOCK_RE.fullmatch(head):
        when = _parse_clock(head, now, force_tomorrow=False)
    else:
        when = now + _parse_duration(head)

    message = rest.strip()
    if not message:
        raise TimeSpecError("Falta el mensaje")
    return when, message

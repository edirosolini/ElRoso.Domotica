"""Parsing of the human time specs accepted by the bot commands.

Accepted shapes, always followed by the message:

    10m sacá la pizza      relative duration (h / m / min / s, combinable)
    1h30m avisar
    23:15 apagá el horno   clock time, rolls to tomorrow if already passed
    mañana 8:00 dentista   explicit tomorrow

Weekly alarms add a day spec in front of the clock ("lun-vie 5:30 arriba").
It is parsed apart, by `parse_weekdays`, because the days pick which occurrence
of the hour fires, not the hour itself.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

TOMORROW_WORDS = {"mañana", "manana"}

# "5.30" is how people write it as often as "5:30"; both mean the same thing.
_CLOCK_RE = re.compile(r"(\d{1,2})[:.](\d{2})")
_DURATION_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)min|(\d+)m)?(?:(\d+)s)?", re.IGNORECASE)


# ISO weekday numbers (1 = Monday), the same ones `datetime.isoweekday()` uses.
WEEKDAYS = {
    "lun": 1, "lunes": 1,
    "mar": 2, "martes": 2,
    "mie": 3, "mié": 3, "miercoles": 3, "miércoles": 3,
    "jue": 4, "jueves": 4,
    "vie": 5, "viernes": 5,
    "sab": 6, "sáb": 6, "sabado": 6, "sábado": 6,
    "dom": 7, "domingo": 7,
}

DAY_GROUPS = {
    "finde": (6, 7),
    "habiles": (1, 2, 3, 4, 5),
    "hábiles": (1, 2, 3, 4, 5),
    "semana": (1, 2, 3, 4, 5),
}

# Short names for the chat. The speaker never says these: a weekly alarm speaks
# its message, and the days only show up written.
DAY_NAMES = {1: "lun", 2: "mar", 3: "mié", 4: "jue", 5: "vie", 6: "sáb", 7: "dom"}


class TimeSpecError(ValueError):
    """The text does not describe a moment we know how to schedule."""


def _split_head(text: str) -> tuple[str, str]:
    parts = text.split(None, 1)
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""


def parse_duration(token: str) -> timedelta:
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
        when = now + parse_duration(head)

    message = rest.strip()
    if not message:
        raise TimeSpecError("Falta el mensaje")
    return when, message


def _expand_range(start: str, end: str) -> tuple[int, ...] | None:
    first, last = WEEKDAYS.get(start), WEEKDAYS.get(end)
    if first is None or last is None:
        return None
    # "vie-lun" wraps through the weekend, so count forward instead of slicing.
    length = (last - first) % 7 + 1
    return tuple((first - 1 + step) % 7 + 1 for step in range(length))


def parse_weekdays(token: str) -> tuple[int, ...] | None:
    """Days meant by "lun-vie", "mar,jue" or "finde"; None if this is not one.

    Returning None instead of raising lets the caller fall back to the other
    shapes: a token that is not a day spec is probably an hour.
    """
    token = token.strip().lower()
    if not token:
        return None

    days: set[int] = set()
    for part in token.split(","):
        part = part.strip()
        if part in DAY_GROUPS:
            days.update(DAY_GROUPS[part])
        elif part in WEEKDAYS:
            days.add(WEEKDAYS[part])
        elif "-" in part:
            start, _, end = part.partition("-")
            expanded = _expand_range(start.strip(), end.strip())
            if expanded is None:
                return None
            days.update(expanded)
        else:
            return None
    return tuple(sorted(days))


def next_weekday(when: datetime, days: tuple[int, ...] | list[int]) -> datetime:
    """The first moment at or after `when` that falls on one of `days`.

    Bounded on purpose: days that match nothing would spin forever otherwise.
    """
    for _ in range(7):
        if when.isoweekday() in days:
            return when
        when += timedelta(days=1)
    raise TimeSpecError("Faltan los días de la semana")


def format_weekdays(days: tuple[int, ...] | list[int]) -> str:
    return ", ".join(DAY_NAMES[day] for day in sorted(days))

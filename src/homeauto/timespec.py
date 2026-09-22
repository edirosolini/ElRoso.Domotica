"""Parser de las formas de tiempo que aceptan los comandos del bot.

Formas aceptadas, siempre seguidas del mensaje:

    10m sacá la pizza      duración relativa (h / m / min / s, combinables)
    1h30m avisar
    23:15 apagá el horno   hora del reloj, rueda a mañana si ya pasó
    mañana 8:00 dentista   mañana explícito

Las alarmas semanales agregan los días delante de la hora ("lun-vie 5:30
arriba"). Se parsean aparte, con `parse_weekdays`, porque los días eligen qué
ocurrencia de la hora dispara, no la hora.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

TOMORROW_WORDS = {"mañana", "manana"}

# "5.30" es como la gente escribe la hora tanto como "5:30"; significan lo mismo.
_CLOCK_RE = re.compile(r"(\d{1,2})[:.](\d{2})")
_DURATION_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)min|(\d+)m)?(?:(\d+)s)?", re.IGNORECASE)


# Días ISO (1 = lunes), la misma numeración que usa `datetime.isoweekday()`.
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

# Nombres cortos para el chat. El parlante nunca los dice: una alarma semanal
# dice su mensaje, y los días solo aparecen escritos.
DAY_NAMES = {1: "lun", 2: "mar", 3: "mié", 4: "jue", 5: "vie", 6: "sáb", 7: "dom"}


class TimeSpecError(ValueError):
    """El texto no describe un momento que se sepa agendar."""


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
    # Una hora que ya pasó hoy significa la próxima, mañana.
    if force_tomorrow or when <= now:
        when += timedelta(days=1)
    return when


def parse_schedule(text: str, now: datetime) -> tuple[datetime, str]:
    """Devuelve cuándo disparar y qué decir, o levanta TimeSpecError."""
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
    # "vie-lun" da la vuelta por el fin de semana: se cuenta hacia adelante.
    length = (last - first) % 7 + 1
    return tuple((first - 1 + step) % 7 + 1 for step in range(length))


def parse_weekdays(token: str) -> tuple[int, ...] | None:
    """Los días que significan "lun-vie", "mar,jue" o "finde"; None si no lo es.

    Devolver None en vez de levantar deja que el llamador pruebe las otras
    formas: un token que no son días probablemente sea una hora.
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
    """El primer momento desde `when` que cae en alguno de `days`.

    Acotado a propósito: unos días que no matchean nada girarían para siempre.
    """
    for _ in range(7):
        if when.isoweekday() in days:
            return when
        when += timedelta(days=1)
    raise TimeSpecError("Faltan los días de la semana")


def format_weekdays(days: tuple[int, ...] | list[int]) -> str:
    return ", ".join(DAY_NAMES[day] for day in sorted(days))

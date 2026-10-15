"""A quién le toca cada ocurrencia de un job que rota por semana ISO."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeauto.schedule.store import Job

_TURN = re.compile(r"^Le toca a (.+?): ")


def week_start(day: date) -> date:
    """El lunes de la semana ISO de `day`."""
    return day - timedelta(days=day.weekday())


def turn_for(job: Job, at: datetime) -> str | None:
    """El nombre al que le toca la ocurrencia de `at`; None si el job no rota."""
    names = job.turns
    if not names or job.rota_from is None:
        return None
    weeks = (week_start(at.date()).toordinal() - week_start(job.rota_from).toordinal()) // 7
    return names[weeks % len(names)]


def with_turn(message: str, name: str) -> str:
    """El mensaje con a quién le toca adelante."""
    return f"Le toca a {name}: {message}"


def turn_in(message: str) -> str | None:
    """El nombre que lleva adelante un mensaje armado con `with_turn`; None si no lleva."""
    match = _TURN.match(message)
    return match.group(1) if match else None

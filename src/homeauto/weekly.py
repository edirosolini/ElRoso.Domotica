"""El balance de la semana sobre el historial de lo que sonó, solo para el chat."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable

from homeauto.schedule.history import DONE, Entry, HistoryStore
from homeauto.schedule.reminders import RING_LIMIT
from homeauto.schedule.store import ALARM, ONCE, REMINDER
from homeauto.timespec import DAY_NAMES

WINDOW = timedelta(days=7)
MAX_MESSAGE = 40
MAX_LINES = 10


def _short(message: str) -> str:
    """El mensaje cortado a `MAX_MESSAGE` caracteres."""
    message = " ".join(message.split())
    if len(message) <= MAX_MESSAGE:
        return message
    return message[: MAX_MESSAGE - 1].rstrip() + "…"


def _when(moment: datetime) -> str:
    return f"{DAY_NAMES[moment.isoweekday()]} {moment:%H:%M}"


def _listed(entries: list[Entry]) -> list[str]:
    """Una línea por aviso, con tope de `MAX_LINES`."""
    lines = [f"• {_short(entry.message)}, {_when(entry.fired_at)}" for entry in entries[:MAX_LINES]]
    if len(entries) > MAX_LINES:
        lines.append(f"… y {len(entries) - MAX_LINES} más")
    return lines


class Weekly:
    def __init__(self, history: HistoryStore, clock: Callable[[], datetime] = datetime.now):
        self.history = history
        self.clock = clock

    def text(self) -> str:
        """El balance de los últimos siete días, o "" si no sonó nada que contar."""
        now = self.clock()
        fired = self.history.between(now - WINDOW, now)
        # Deja afuera los timers, salvo lo pospuesto de un recordatorio que repite.
        repeating = {entry.message for entry in fired if entry.kind == REMINDER and entry.repeat != ONCE}
        entries = [
            entry
            for entry in fired
            if not (entry.kind == REMINDER and entry.repeat == ONCE) or entry.message in repeating
        ]
        blocks = [
            block
            for block in (
                self._reminders(entries),
                self._unanswered(entries, now),
                self._unsaid(entries),
            )
            if block
        ]
        if not blocks:
            return ""
        return "\n\n".join(["📊 La semana", *blocks])

    @staticmethod
    def _reminders(entries: list[Entry]) -> str:
        """Cuántos días se marcó hecho cada recordatorio, sobre los días que sonó."""
        days: dict[str, dict[date, bool]] = {}
        for entry in entries:
            if entry.kind != REMINDER:
                continue
            per_day = days.setdefault(entry.message, {})
            day = entry.fired_at.date()
            per_day[day] = per_day.get(day, False) or entry.closed == DONE
        if not days:
            return ""
        lines = [
            f"{_short(message)}: {sum(per_day.values())} de {len(per_day)}"
            for message, per_day in days.items()
        ]
        return "\n".join(["✅ Recordatorios", *lines])

    @staticmethod
    def _unanswered(entries: list[Entry], now: datetime) -> str:
        """Las alarmas que sonaron hasta el final sin que nadie las apagara."""
        rang = [
            entry
            for entry in entries
            if entry.kind == ALARM
            and entry.closed is None
            and entry.nags >= 1
            and entry.fired_at < now - RING_LIMIT
        ]
        if not rang:
            return ""
        return "\n".join([f"⏰ Alarmas que nadie apagó: {len(rang)}", *_listed(rang)])

    @staticmethod
    def _unsaid(entries: list[Entry]) -> str:
        """Lo que sonó sin salir por el parlante."""
        unsaid = [entry for entry in entries if not entry.announced]
        if not unsaid:
            return ""
        return "\n".join([f"🔇 No salieron por el parlante: {len(unsaid)}", *_listed(unsaid)])

"""Lo que muestra la pantalla: eventos por rango, clima, listas y descanso."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, tzinfo
from typing import Callable

from homeauto.lists import LISTS
from homeauto.schedule.month import (
    ALARM_ITEM,
    REMINDER_ITEM,
    TIMER_ITEM,
    Item,
    from_history,
    occurrences_between,
)
from homeauto.weather import WeatherError, describe_code

log = logging.getLogger(__name__)

MAX_RANGE = timedelta(days=62)
CALENDAR_TTL = timedelta(minutes=5)
WEATHER_TTL = timedelta(minutes=15)
# Rangos distintos que se guardan a la vez; pasado eso se tira el más viejo.
MAX_CACHED_RANGES = 32

HOUSE = "casa"
GOOGLE = "google"

# Los colores de Google Calendar, en orden de alias.
PALETTE = (
    "#039be5", "#33b679", "#8e24aa", "#e67c73",
    "#f6bf26", "#f4511e", "#3f51b5", "#0b8043",
)
KIND_ICONS = {ALARM_ITEM: "⏰", REMINDER_ITEM: "📌", TIMER_ITEM: "⏲️"}
KIND_COLORS = {ALARM_ITEM: "#d93025", REMINDER_ITEM: "#1a73e8", TIMER_ITEM: "#e37400"}
PAST_COLOR = "#9aa0a6"


class RangeError(ValueError):
    """El rango pedido está invertido o es demasiado largo."""


def marks(item: Item) -> list[str]:
    """Cómo terminó un aviso que ya sonó."""
    found = []
    if item.done:
        found.append(f"✅ {item.done_by or ''}".rstrip())
    if item.nags:
        found.append(f"🔔×{item.nags}")
    if item.snoozed:
        found.append("💤 pospuesto")
    if item.cancelled:
        found.append("✖️ cancelado")
    if item.silent:
        found.append("⚠️ no sonó")
    return found


def _house_event(item: Item) -> dict:
    """Un ítem de la casa en el formato de evento de FullCalendar."""
    found = marks(item)
    title = f"{KIND_ICONS[item.kind]} {item.message}"
    if found:
        title = f"{title} · {' '.join(found)}"
    return {
        "title": title,
        "start": item.at.isoformat(),
        "allDay": False,
        "editable": False,
        "color": PAST_COLOR if item.past else KIND_COLORS[item.kind],
        "classNames": ["casa", item.kind] + (["past"] if item.past else []),
        "extendedProps": {"source": HOUSE, "kind": item.kind, "past": item.past, "marks": found},
    }


class Board:
    """Arma lo que piden la agenda y el kiosco, sin saber de HTTP."""

    def __init__(
        self,
        store,
        history,
        clock: Callable[[], datetime] = datetime.now,
        timezone: tzinfo | None = None,
        calendar=None,
        weather=None,
        lists=None,
        quiet=None,
    ):
        self.store = store
        self.history = history
        self.clock = clock
        self.timezone = timezone or datetime.now().astimezone().tzinfo
        self.calendar = calendar
        self.weather = weather
        self.lists = lists
        self.quiet = quiet
        self._lock = threading.Lock()
        self._calendar_cache: dict[tuple[datetime, datetime], tuple[datetime, list, list]] = {}
        self._weather_cache: tuple[datetime, dict] | None = None

    @property
    def aliases(self) -> list[str]:
        """Los calendarios en el orden de la config; las URLs no salen de acá."""
        return list(getattr(self.calendar, "sources", {}) or {})

    def _color(self, alias: str) -> str:
        aliases = self.aliases
        index = aliases.index(alias) if alias in aliases else len(aliases)
        return PALETTE[index % len(PALETTE)]

    def events(self, start: datetime, end: datetime) -> dict:
        """Lo de la casa y de Google entre `start` y `end`, en hora local sin zona."""
        if end <= start:
            raise RangeError("el final tiene que ser posterior al principio")
        if end - start > MAX_RANGE:
            raise RangeError(f"el rango no puede pasar de {MAX_RANGE.days} días")

        now = self.clock()
        timed = [(item.at, _house_event(item)) for item in self._house(start, end, now)]
        google, problems = self._google(start, end, now)
        timed.extend(google)
        timed.sort(key=lambda pair: (pair[0], pair[1]["title"]))
        return {
            "events": [event for _, event in timed],
            "calendars": [{"name": alias, "color": self._color(alias)} for alias in self.aliases],
            "problems": problems,
        }

    def _house(self, start: datetime, end: datetime, now: datetime) -> list[Item]:
        past = []
        if start < now:
            past = [from_history(entry) for entry in self.history.between(start, min(end, now))]
        return past + occurrences_between(self.store.pending(), start, end, now)

    def _google(self, start: datetime, end: datetime, now: datetime) -> tuple[list, list[str]]:
        if self.calendar is None:
            return [], []
        key = (start, end)
        with self._lock:
            cached = self._calendar_cache.get(key)
        if cached and timedelta(0) <= now - cached[0] < CALENDAR_TTL:
            return cached[1], cached[2]

        found, problems = self._read_calendar(start, end)
        with self._lock:
            self._calendar_cache = {
                k: v for k, v in self._calendar_cache.items() if now - v[0] < CALENDAR_TTL
            }
            while len(self._calendar_cache) >= MAX_CACHED_RANGES:
                self._calendar_cache.pop(next(iter(self._calendar_cache)))
            self._calendar_cache[key] = (now, found, problems)
        return found, problems

    def _read_calendar(self, start: datetime, end: datetime) -> tuple[list, list[str]]:
        """Los eventos de Google y qué calendarios no se pudieron leer, solo por alias."""
        try:
            read = self.calendar.between(
                start.replace(tzinfo=self.timezone), end.replace(tzinfo=self.timezone)
            )
            broken = [problem.split(":", 1)[0] for problem in self.calendar.last_problems]
        except Exception:  # noqa: BLE001
            log.warning("could not read any calendar", exc_info=True)
            read, broken = [], self.aliases
        found = [(self._naive(event.start), self._google_event(event)) for event in read]
        return found, [f"No pude leer el calendario {alias}." for alias in broken]

    def _naive(self, moment: datetime) -> datetime:
        """La hora local sin zona, como guarda la casa sus jobs."""
        if moment.tzinfo is None:
            return moment
        return moment.astimezone(self.timezone).replace(tzinfo=None)

    def _google_event(self, event) -> dict:
        """Un evento de Google en el formato de FullCalendar, de solo lectura."""
        if event.all_day:
            start: str = self._naive(event.start).date().isoformat()
            end: str = self._naive(event.end).date().isoformat()
        else:
            start = self._naive(event.start).isoformat()
            end = self._naive(event.end).isoformat()
        return {
            "title": event.summary,
            "start": start,
            "end": end,
            "allDay": event.all_day,
            "editable": False,
            "color": self._color(event.calendar),
            "classNames": [GOOGLE],
            "extendedProps": {
                "source": GOOGLE,
                "calendar": event.calendar,
                "location": event.location,
            },
        }

    def screen(self) -> dict:
        """El estado del kiosco: hora del servidor, descanso, clima y listas."""
        now = self.clock()
        today, problems = self._today(now)
        weather = self._forecast(now)
        if self.weather is not None and weather is None:
            problems.append("No pude consultar el clima.")
        return {
            "today": today,
            "now": now.replace(tzinfo=self.timezone).isoformat()
            if now.tzinfo is None
            else now.isoformat(),
            "quiet": bool(self.quiet.is_quiet(now)) if self.quiet is not None else False,
            "weather": weather,
            "lists": {name: self.lists.items(name) for name in LISTS} if self.lists else {},
            "problems": problems,
        }

    def _today(self, now: datetime) -> tuple[list[dict], list[str]]:
        """Lo de hoy, de la casa y de Google, con lo ya pasado marcado."""
        local = self._naive(now)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        found = self.events(start, start + timedelta(days=1))
        today = []
        for event in found["events"]:
            if event["allDay"]:
                time = None
                past = datetime.fromisoformat(event["end"]).date() <= local.date()
            else:
                begins = datetime.fromisoformat(event["start"])
                time = begins.strftime("%H:%M")
                if event["extendedProps"]["source"] == HOUSE:
                    past = event["extendedProps"]["past"]
                else:
                    past = datetime.fromisoformat(event["end"]) <= local
            today.append(
                {"time": time, "title": event["title"], "past": past, "color": event["color"]}
            )
        return today, list(found["problems"])

    def _forecast(self, now: datetime) -> dict | None:
        """El clima del día, cacheado; una falla no se cachea."""
        if self.weather is None:
            return None
        with self._lock:
            cached = self._weather_cache
        if cached and timedelta(0) <= now - cached[0] < WEATHER_TTL:
            return cached[1]
        try:
            forecast = self.weather.now()
        except WeatherError:
            return None
        data = {
            "temperature": forecast.temperature,
            "feels_like": forecast.feels_like,
            "maximum": forecast.maximum,
            "minimum": forecast.minimum,
            "rain_chance": forecast.rain_chance,
            "sky": describe_code(forecast.code),
        }
        with self._lock:
            self._weather_cache = (now, data)
        return data

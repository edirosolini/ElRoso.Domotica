"""Reading Google Calendar through its private iCal address.

Chosen over the Calendar API on purpose: this is read-only, and the secret URL
needs no OAuth project, no consent screen and no refresh tokens. The cost is
that Google caches that URL, so a brand new event can take a while to show up.

The secret URL is a credential: whoever holds it reads the whole calendar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

TIMEOUT = 20
CACHE_SECONDS = 300


class CalendarError(Exception):
    """No calendar could be read."""


@dataclass(frozen=True)
class Event:
    uid: str
    summary: str
    start: datetime
    end: datetime
    all_day: bool
    calendar: str
    location: str = ""

    @property
    def key(self) -> str:
        """Stable per occurrence: a weekly event fires many times."""
        return f"{self.calendar}:{self.uid}:{self.start.isoformat()}"


def fetch_url(url: str) -> str:
    """The real download. Imported lazily so tests never touch the network."""
    import requests

    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


class CalendarClient:
    def __init__(
        self,
        sources: dict[str, str],
        timezone: ZoneInfo,
        fetch: Callable[[str], str] = fetch_url,
        cache_seconds: int = CACHE_SECONDS,
    ):
        self.sources = dict(sources)
        self.timezone = timezone
        self.fetch = fetch
        self.cache_seconds = cache_seconds
        self.last_problems: list[str] = []
        self._cache: dict[str, tuple[float, str]] = {}

    def _raw(self, alias: str, url: str) -> str:
        import time as clock

        cached = self._cache.get(alias)
        now = clock.monotonic()
        if cached and now - cached[0] < self.cache_seconds:
            return cached[1]

        text = self.fetch(url)
        self._cache[alias] = (now, text)
        return text

    def _to_local(self, value) -> tuple[datetime, bool]:
        """Normalize whatever the ics carried into an aware local datetime."""
        if isinstance(value, datetime):
            if value.tzinfo is None:  # floating time: read it as local
                return value.replace(tzinfo=self.timezone), False
            return value.astimezone(self.timezone), False
        # A bare date means an all-day event.
        return datetime.combine(value, time.min, tzinfo=self.timezone), True

    def _events_of(self, alias: str, url: str, start: datetime, end: datetime) -> list[Event]:
        import icalendar
        import recurring_ical_events

        calendar = icalendar.Calendar.from_ical(self._raw(alias, url))
        found = []
        for component in recurring_ical_events.of(calendar).between(start, end):
            begins, all_day = self._to_local(component.get("DTSTART").dt)
            raw_end = component.get("DTEND")
            finishes = self._to_local(raw_end.dt)[0] if raw_end else begins + timedelta(hours=1)
            found.append(
                Event(
                    uid=str(component.get("UID", "")),
                    summary=str(component.get("SUMMARY", "(sin título)")),
                    start=begins,
                    end=finishes,
                    all_day=all_day,
                    calendar=alias,
                    location=str(component.get("LOCATION", "") or ""),
                )
            )
        return found

    def between(self, start: datetime, end: datetime) -> list[Event]:
        """Every occurrence in the window, from every calendar, sorted."""
        events: list[Event] = []
        problems: list[str] = []

        for alias, url in self.sources.items():
            try:
                events.extend(self._events_of(alias, url, start, end))
            except Exception as exc:  # noqa: BLE001 - un calendario roto no tapa los otros
                log.warning("no pude leer el calendario '%s': %s", alias, exc)
                problems.append(f"{alias}: {exc}")

        self.last_problems = problems
        if problems and len(problems) == len(self.sources):
            raise CalendarError("; ".join(problems))

        return sorted(events, key=lambda event: (event.start, event.summary))

    def day(self, moment: datetime) -> list[Event]:
        start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.between(start, start + timedelta(days=1))

    def rest_of_day(self, moment: datetime) -> list[Event]:
        end = moment.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return [event for event in self.between(moment, end) if event.end > moment]

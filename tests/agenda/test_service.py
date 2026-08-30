from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from homeauto.agenda.ical import CalendarError, Event
from homeauto.agenda.service import AgendaService

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
NOW = datetime(2026, 8, 30, 15, 0, tzinfo=TZ)


def event(day, hour, summary):
    start = datetime(2026, 8, day, hour, 0, tzinfo=TZ)
    return Event(f"{summary}@t", summary, start, start + timedelta(hours=1), False, "personal")


class FakeCalendar:
    def __init__(self, events=(), boom=None):
        self.events = list(events)
        self.boom = boom
        self.windows = []

    def between(self, start, end):
        if self.boom:
            raise self.boom
        self.windows.append((start, end))
        return sorted((e for e in self.events if start <= e.start < end), key=lambda e: e.start)

    def rest_of_day(self, moment):
        end = moment.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return self.between(moment, end)

    def day(self, moment):
        start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.between(start, start + timedelta(days=1))


def service(calendar):
    return AgendaService(calendar=calendar, clock=lambda: NOW)


def test_today_only_shows_what_is_left():
    calendar = FakeCalendar([event(30, 9, "Ya pasó"), event(30, 18, "Cena")])

    text = service(calendar).spoken("hoy")

    assert "Cena" in text
    assert "Ya pasó" not in text


def test_tomorrow_shows_the_whole_day():
    calendar = FakeCalendar([event(31, 8, "Temprano"), event(31, 20, "Tarde")])

    text = service(calendar).spoken("mañana")

    assert "Temprano" in text and "Tarde" in text


def test_tomorrow_without_accent_works():
    calendar = FakeCalendar([event(31, 8, "Temprano")])

    assert "Temprano" in service(calendar).spoken("manana")


def test_an_empty_day_is_said_politely():
    text = service(FakeCalendar()).spoken("hoy")

    assert "nada" in text.lower()


def test_an_unknown_word_is_rejected():
    with pytest.raises(ValueError, match="hoy"):
        service(FakeCalendar()).spoken("el jueves que viene")


def test_a_calendar_failure_bubbles_up():
    with pytest.raises(CalendarError):
        service(FakeCalendar(boom=CalendarError("sin red"))).spoken("hoy")


def test_the_full_day_briefing_ignores_the_current_time():
    calendar = FakeCalendar([event(30, 9, "Temprano"), event(30, 18, "Cena")])

    text = service(calendar).briefing()

    assert "Temprano" in text and "Cena" in text


# --- pulido de la redacción ---

def with_dentist():
    return FakeCalendar([event(30, 18, "Dentista")])


def test_the_wording_is_polished_when_a_polisher_is_given():
    calls = []

    def polish(text, must_keep=()):
        calls.append((text, tuple(must_keep)))
        return "redacción mejorada"

    subject = AgendaService(calendar=with_dentist(), clock=lambda: NOW, polish=polish)

    assert subject.spoken("hoy") == "redacción mejorada"
    assert "Dentista" in calls[0][1], "el título del evento no se puede perder"


def test_the_briefing_is_polished_too():
    subject = AgendaService(
        calendar=with_dentist(),
        clock=lambda: NOW,
        polish=lambda text, must_keep=(): "mejor",
    )

    assert subject.briefing() == "mejor"


def test_without_a_polisher_the_text_is_untouched():
    assert "Dentista" in AgendaService(calendar=with_dentist(), clock=lambda: NOW).spoken("hoy")

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from homeauto.agenda.ical import CalendarClient, CalendarError

TZ = ZoneInfo("America/Argentina/Buenos_Aires")

# 2026-08-25 es martes; 2026-08-29, sábado.
ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//prueba//ES
BEGIN:VEVENT
UID:simple@test
DTSTART;TZID=America/Argentina/Buenos_Aires:20260830T100000
DTEND;TZID=America/Argentina/Buenos_Aires:20260830T110000
SUMMARY:Reunión con el equipo
LOCATION:Oficina
END:VEVENT
BEGIN:VEVENT
UID:allday@test
DTSTART;VALUE=DATE:20260830
DTEND;VALUE=DATE:20260831
SUMMARY:Feriado
END:VEVENT
BEGIN:VEVENT
UID:weekly@test
DTSTART;TZID=America/Argentina/Buenos_Aires:20260825T090000
DTEND;TZID=America/Argentina/Buenos_Aires:20260825T093000
RRULE:FREQ=WEEKLY;BYDAY=TU
EXDATE;TZID=America/Argentina/Buenos_Aires:20260901T090000
SUMMARY:Daily standup
END:VEVENT
END:VCALENDAR
"""


def client(sources=None, payloads=None, boom=None):
    sources = sources or {"personal": "https://ejemplo/a.ics"}
    payloads = payloads if payloads is not None else {"personal": ICS}
    calls = []

    def fetch(url):
        calls.append(url)
        if boom:
            raise boom
        for alias, source in sources.items():
            if source == url:
                payload = payloads.get(alias)
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError("url inesperada")

    built = CalendarClient(sources, timezone=TZ, fetch=fetch)
    built.calls = calls
    return built


def day(y, m, d, h=0, minute=0):
    return datetime(y, m, d, h, minute, tzinfo=TZ)


def test_reads_a_timed_event_in_local_time():
    events = client().between(day(2026, 8, 30), day(2026, 8, 31))

    reunion = next(e for e in events if "Reunión" in e.summary)
    assert reunion.start == day(2026, 8, 30, 10, 0)
    assert reunion.end == day(2026, 8, 30, 11, 0)
    assert reunion.all_day is False
    assert reunion.location == "Oficina"


def test_marks_all_day_events():
    events = client().between(day(2026, 8, 30), day(2026, 8, 31))

    feriado = next(e for e in events if e.summary == "Feriado")
    assert feriado.all_day is True


def test_expands_a_recurring_event():
    events = client().between(day(2026, 9, 7), day(2026, 9, 10))

    assert [e.summary for e in events] == ["Daily standup"]
    assert events[0].start == day(2026, 9, 8, 9, 0)


def test_an_excluded_occurrence_does_not_appear():
    events = client().between(day(2026, 9, 1), day(2026, 9, 2))

    assert events == [], "el 1 de septiembre está en EXDATE"


def test_events_come_sorted_by_start():
    events = client().between(day(2026, 8, 30), day(2026, 8, 31))

    assert [e.start for e in events] == sorted(e.start for e in events)


def test_each_event_knows_its_calendar():
    events = client().between(day(2026, 8, 30), day(2026, 8, 31))

    assert {e.calendar for e in events} == {"personal"}


def test_several_calendars_are_merged():
    sources = {"personal": "https://a/a.ics", "trabajo": "https://b/b.ics"}
    other = ICS.replace("simple@test", "otro@test").replace("Reunión con el equipo", "Dentista")
    merged = client(sources, {"personal": ICS, "trabajo": other})

    events = merged.between(day(2026, 8, 30), day(2026, 8, 31))

    assert {e.calendar for e in events} == {"personal", "trabajo"}
    assert any(e.summary == "Dentista" for e in events)


def test_a_broken_calendar_does_not_hide_the_others():
    sources = {"personal": "https://a/a.ics", "roto": "https://b/b.ics"}
    partial = client(sources, {"personal": ICS, "roto": TimeoutError("se cayó")})

    events = partial.between(day(2026, 8, 30), day(2026, 8, 31))

    assert any(e.summary == "Feriado" for e in events)
    assert partial.last_problems, "el fallo tiene que quedar registrado"
    assert "roto" in partial.last_problems[0]


def test_when_every_calendar_fails_it_raises():
    with pytest.raises(CalendarError):
        client(boom=TimeoutError("sin red")).between(day(2026, 8, 30), day(2026, 8, 31))


def test_garbage_instead_of_a_calendar_is_reported():
    with pytest.raises(CalendarError):
        client(payloads={"personal": "esto no es un ics"}).between(day(2026, 8, 30), day(2026, 8, 31))


def test_the_calendar_is_not_downloaded_on_every_question():
    reused = client()

    reused.between(day(2026, 8, 30), day(2026, 8, 31))
    reused.between(day(2026, 8, 31), day(2026, 9, 1))

    assert len(reused.calls) == 1, "Google sirve el mismo ics: bajarlo dos veces es desperdicio"


def test_the_cache_expires():
    reused = client()
    reused.cache_seconds = 0

    reused.between(day(2026, 8, 30), day(2026, 8, 31))
    reused.between(day(2026, 8, 31), day(2026, 9, 1))

    assert len(reused.calls) == 2

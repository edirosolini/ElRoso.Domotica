"""El tablero de la pantalla: eventos por rango, clima, listas y descanso."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from homeauto.agenda.ical import CalendarClient
from homeauto.lists import ListStore
from homeauto.quiet import Hush, HushStore, QuietHours
from homeauto.schedule.history import HistoryStore
from homeauto.schedule.store import DAILY, REMINDER, Store
from homeauto.weather import WeatherClient
from homeauto.web.board import KIND_COLORS, MAX_RANGE, PALETTE, Board, RangeError, sky_icon

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
NOW = datetime(2026, 10, 5, 12, 0)  # lunes
SECRET = "https://calendar.google.com/calendar/ical/secreto-privado/basic.ics"
OTHER = "https://calendar.google.com/calendar/ical/otro-privado/basic.ics"

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//prueba//ES
BEGIN:VEVENT
UID:dentista@test
DTSTART;TZID=America/Argentina/Buenos_Aires:20261006T100000
DTEND;TZID=America/Argentina/Buenos_Aires:20261006T110000
SUMMARY:<b>Dentista</b>
LOCATION:Consultorio
END:VEVENT
BEGIN:VEVENT
UID:feriado@test
DTSTART;VALUE=DATE:20261012
DTEND;VALUE=DATE:20261013
SUMMARY:Feriado
END:VEVENT
END:VCALENDAR
"""

ICS_OTHER = (
    ICS.replace("dentista@test", "otro@test")
    .replace("<b>Dentista</b>", "Fútbol")
    .replace("feriado@test", "feriado-otro@test")
)

OPEN_METEO = {
    "current": {
        "temperature_2m": 21.4,
        "apparent_temperature": 20.6,
        "relative_humidity_2m": 60,
        "weather_code": 1,
    },
    "daily": {
        "temperature_2m_max": [24.2, 26.0],
        "temperature_2m_min": [12.7, 14.0],
        "precipitation_probability_max": [10, 70],
        "weather_code": [1, 61],
    },
}


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


def calendar_client(payloads, calls):
    sources = {"personal": SECRET, "familia": OTHER}

    def fetch(url):
        calls.append(url)
        payload = payloads[url]
        if isinstance(payload, Exception):
            raise payload
        return payload

    # Sin cache propio: el que cachea en estos tests es el tablero.
    return CalendarClient(sources, timezone=TZ, fetch=fetch, cache_seconds=0)


def weather_client(calls, fail=False):
    def fetch(latitude, longitude):
        calls.append((latitude, longitude))
        if fail:
            raise ConnectionError("sin red")
        return OPEN_METEO

    return WeatherClient(latitude=-34.6, longitude=-58.4, fetch=fetch)


@pytest.fixture
def parts(tmp_path):
    db = tmp_path / "jobs.db"
    return {
        "store": Store(db),
        "history": HistoryStore(db),
        "lists": ListStore(db),
        "hush": HushStore(db),
    }


def board(parts, clock=None, calendar=None, weather=None, quiet=None):
    return Board(
        store=parts["store"],
        history=parts["history"],
        clock=clock or Clock(),
        timezone=TZ,
        calendar=calendar,
        weather=weather,
        lists=parts["lists"],
        quiet=quiet,
    )


WEEK = (datetime(2026, 10, 5), datetime(2026, 10, 12))


def both_calendars(calls=None):
    return calendar_client({SECRET: ICS, OTHER: ICS_OTHER}, [] if calls is None else calls)


# --- lo de la casa ---


def test_a_daily_reminder_fills_the_range_from_now(parts):
    parts["store"].add(42, datetime(2026, 10, 5, 21, 0), "la pastilla", repeat=DAILY, kind=REMINDER)

    found = board(parts).events(*WEEK)["events"]

    assert [event["start"] for event in found] == [
        f"2026-10-{day:02d}T21:00:00" for day in range(5, 12)
    ]
    assert all("la pastilla" in event["title"] for event in found)
    assert all(event["extendedProps"]["kind"] == "reminder" for event in found)
    assert all(event["extendedProps"]["source"] == "casa" for event in found)
    assert all(event["editable"] is False for event in found)


def test_what_is_still_to_ring_carries_its_job_for_editing(parts):
    job = parts["store"].add(42, datetime(2026, 10, 6, 7, 0), "arriba")
    parts["history"].record(9, 42, "alarm", "once", "ya sonó", datetime(2026, 10, 5, 8, 0))

    found = board(parts).events(*WEEK)["events"]

    by_start = {event["start"]: event["extendedProps"] for event in found}
    assert by_start["2026-10-06T07:00:00"]["job"] == job.id
    assert by_start["2026-10-05T08:00:00"]["job"] is None


def test_what_sounded_carries_how_it_ended(parts):
    history = parts["history"]
    history.record(7, 42, REMINDER, DAILY, "el colegio", datetime(2026, 10, 2, 7, 0))
    history.mark_announced(7)
    history.mark_nag(7)
    history.mark_nag(7)
    history.mark_done(7, datetime(2026, 10, 2, 7, 3), "Eze")
    history.record(8, 42, "alarm", "once", "arriba", datetime(2026, 10, 3, 7, 0))

    found = board(parts).events(datetime(2026, 9, 28), datetime(2026, 10, 5))["events"]

    colegio, arriba = found
    assert colegio["extendedProps"]["past"] is True
    assert colegio["extendedProps"]["marks"] == ["✅ Eze", "🔔×2"]
    assert "✅ Eze" in colegio["title"] and "🔔×2" in colegio["title"]
    assert "⚠️ no sonó" in arriba["extendedProps"]["marks"]


def test_today_mixes_what_sounded_with_what_is_coming_without_repeating(parts):
    parts["history"].record(1, 42, "alarm", DAILY, "arriba", datetime(2026, 10, 5, 8, 0))
    parts["store"].add(42, datetime(2026, 10, 6, 8, 0), "arriba", repeat=DAILY)
    parts["store"].add(42, datetime(2026, 10, 5, 18, 0), "la pizza")

    found = board(parts).events(datetime(2026, 10, 5), datetime(2026, 10, 6))["events"]

    assert [(e["start"][11:13], e["extendedProps"]["past"]) for e in found] == [
        ("08", True),
        ("18", False),
    ]


def test_a_past_range_shows_only_the_history(parts):
    parts["store"].add(42, datetime(2026, 10, 6, 8, 0), "arriba", repeat=DAILY)
    parts["history"].record(1, 42, "alarm", "once", "viejo", datetime(2026, 9, 10, 8, 0))

    found = board(parts).events(datetime(2026, 9, 1), datetime(2026, 10, 1))["events"]

    assert [e["start"] for e in found] == ["2026-09-10T08:00:00"]


def test_history_after_now_is_not_shown(parts):
    parts["history"].record(9, 42, "alarm", "once", "futuro", NOW + timedelta(hours=1))

    assert board(parts).events(*WEEK)["events"] == []


def test_snoozed_and_cancelled_are_marked(parts):
    history = parts["history"]
    at = datetime(2026, 10, 1, 9, 0)
    history.record(1, 42, "alarm", "once", "arriba", at)
    history.mark_closed(1, "snooze", at)
    history.record(2, 42, "reminder", "once", "pizza", at + timedelta(hours=1))
    history.mark_closed(2, "cancel", at)

    snoozed, cancelled = board(parts).events(datetime(2026, 10, 1), datetime(2026, 10, 2))["events"]

    assert "💤 pospuesto" in snoozed["extendedProps"]["marks"]
    assert "✖️ cancelado" in cancelled["extendedProps"]["marks"]


# --- Google Calendar ---


def test_calendar_events_come_read_only_with_their_color(parts):
    answer = board(parts, calendar=both_calendars()).events(*WEEK)

    [dentist] = [e for e in answer["events"] if e["title"] == "<b>Dentista</b>"]
    assert dentist["start"] == "2026-10-06T10:00:00"
    assert dentist["end"] == "2026-10-06T11:00:00"
    assert dentist["allDay"] is False
    assert dentist["editable"] is False
    assert dentist["color"] == PALETTE[0]
    assert dentist["extendedProps"] == {
        "source": "google", "calendar": "personal", "location": "Consultorio"
    }
    [football] = [e for e in answer["events"] if e["title"] == "Fútbol"]
    assert football["color"] == PALETTE[1]
    assert answer["calendars"] == [
        {"name": "personal", "color": PALETTE[0]},
        {"name": "familia", "color": PALETTE[1]},
    ]
    assert answer["problems"] == []


def test_an_all_day_event_is_a_date(parts):
    found = board(parts, calendar=both_calendars()).events(
        datetime(2026, 10, 12), datetime(2026, 10, 13)
    )["events"]

    holiday = found[0]
    assert holiday["title"] == "Feriado"
    assert holiday["allDay"] is True
    assert (holiday["start"], holiday["end"]) == ("2026-10-12", "2026-10-13")


def test_a_broken_calendar_does_not_hide_the_others(parts):
    calendar = calendar_client(
        {SECRET: ConnectionError(f"404 for url: {SECRET}"), OTHER: ICS_OTHER}, []
    )

    answer = board(parts, calendar=calendar).events(*WEEK)

    assert any(e["title"] == "Fútbol" for e in answer["events"])
    assert answer["problems"] == ["No pude leer el calendario personal."]


def test_every_calendar_broken_still_shows_the_house(parts):
    parts["store"].add(42, datetime(2026, 10, 6, 8, 0), "arriba")
    calendar = calendar_client(
        {SECRET: ConnectionError(f"404 for url: {SECRET}"), OTHER: ConnectionError("caído")}, []
    )

    answer = board(parts, calendar=calendar).events(*WEEK)

    assert [e["extendedProps"]["source"] for e in answer["events"]] == ["casa"]
    assert answer["problems"] == [
        "No pude leer el calendario personal.",
        "No pude leer el calendario familia.",
    ]


def test_the_private_urls_never_leave(parts):
    calendar = calendar_client(
        {SECRET: ConnectionError(f"404 for url: {SECRET}"), OTHER: ICS_OTHER}, []
    )

    dumped = json.dumps(board(parts, calendar=calendar).events(*WEEK))

    assert "secreto-privado" not in dumped
    assert "otro-privado" not in dumped
    assert "http" not in dumped


def test_calendar_events_are_cached_for_five_minutes_per_range(parts):
    calls = []
    clock = Clock()
    built = board(parts, clock=clock, calendar=both_calendars(calls))

    built.events(*WEEK)
    built.events(*WEEK)
    assert len(calls) == 2

    built.events(datetime(2026, 10, 12), datetime(2026, 10, 19))
    assert len(calls) == 4

    clock.now = NOW + timedelta(minutes=4, seconds=59)
    built.events(*WEEK)
    assert len(calls) == 4

    clock.now = NOW + timedelta(minutes=5, seconds=1)
    built.events(*WEEK)
    assert len(calls) == 6


def test_the_house_is_not_cached(parts):
    built = board(parts, calendar=both_calendars())
    built.events(*WEEK)

    parts["store"].add(42, datetime(2026, 10, 6, 8, 0), "nueva")

    assert any("nueva" in e["title"] for e in built.events(*WEEK)["events"])


def test_the_events_come_sorted(parts):
    parts["store"].add(42, datetime(2026, 10, 6, 9, 0), "después del dentista")
    parts["store"].add(42, datetime(2026, 10, 6, 8, 0), "antes del dentista")

    found = board(parts, calendar=both_calendars()).events(
        datetime(2026, 10, 6), datetime(2026, 10, 7)
    )["events"]

    assert [e["start"][11:16] for e in found] == ["08:00", "09:00", "10:00", "10:00"]


# --- el rango ---


def test_an_inverted_range_is_refused(parts):
    with pytest.raises(RangeError):
        board(parts).events(datetime(2026, 10, 12), datetime(2026, 10, 5))


def test_a_range_longer_than_the_limit_is_refused(parts):
    start = datetime(2026, 10, 1)

    board(parts).events(start, start + MAX_RANGE)
    with pytest.raises(RangeError):
        board(parts).events(start, start + MAX_RANGE + timedelta(days=1))


def test_the_limit_fits_a_month_with_its_neighbour_weeks():
    assert MAX_RANGE == timedelta(days=62)


# --- la pantalla ---


def test_the_screen_has_the_weather_the_lists_and_the_hour(parts):
    parts["lists"].add("compras", ["leche", "pan"])
    parts["lists"].add("pendientes", ["llamar al plomero"])

    answer = board(parts, weather=weather_client([])).screen()

    assert answer["now"] == "2026-10-05T12:00:00-03:00"
    assert answer["weather"]["temperature"] == 21
    assert answer["weather"]["maximum"] == 24
    assert answer["weather"]["minimum"] == 13
    assert answer["weather"]["rain_chance"] == 10
    assert answer["weather"]["sky"]
    assert {name: [entry["text"] for entry in entries]
            for name, entries in answer["lists"].items()} == {
        "compras": ["leche", "pan"], "pendientes": ["llamar al plomero"]
    }
    assert answer["quiet"] is False
    assert answer["problems"] == []


def test_each_list_item_carries_its_id_for_crossing_it_out(parts):
    parts["lists"].add("compras", ["leche"])
    [(item_id, _)] = parts["lists"].entries("compras")

    answer = board(parts).screen()

    assert answer["lists"]["compras"] == [{"id": item_id, "text": "leche"}]
    assert answer["lists"]["pendientes"] == []


def test_the_weather_is_cached_for_fifteen_minutes(parts):
    calls = []
    clock = Clock()
    built = board(parts, clock=clock, weather=weather_client(calls))

    built.screen()
    clock.now = NOW + timedelta(minutes=14)
    built.screen()
    assert len(calls) == 1

    clock.now = NOW + timedelta(minutes=15, seconds=1)
    built.screen()
    assert len(calls) == 2


def test_without_weather_the_screen_still_answers(parts):
    answer = board(parts, weather=weather_client([], fail=True)).screen()

    assert answer["weather"] is None
    assert answer["problems"] == ["No pude consultar el clima."]


def test_a_failed_weather_is_retried_on_the_next_poll(parts):
    calls = []
    built = board(parts, weather=weather_client(calls, fail=True))

    built.screen()
    built.screen()

    assert len(calls) == 2


def test_the_screen_goes_dark_in_the_quiet_hours(parts):
    clock = Clock(datetime(2026, 10, 5, 23, 0))
    quiet = Hush(hours=QuietHours.parse("22:00", "05:25"), store=parts["hush"], clock=clock)

    assert board(parts, clock=clock, quiet=quiet).screen()["quiet"] is True

    clock.now = NOW
    assert board(parts, clock=clock, quiet=quiet).screen()["quiet"] is False


def test_a_silence_on_demand_also_darkens_the_screen(parts):
    clock = Clock()
    quiet = Hush(hours=QuietHours.parse("22:00", "05:25"), store=parts["hush"], clock=clock)
    quiet.start(timedelta(hours=1))

    assert board(parts, clock=clock, quiet=quiet).screen()["quiet"] is True


def test_the_screen_has_today_from_the_house_and_google(parts):
    clock = Clock(datetime(2026, 10, 6, 10, 30))
    history = parts["history"]
    history.record(7, 42, REMINDER, DAILY, "la pastilla", datetime(2026, 10, 6, 8, 0))
    history.mark_announced(7)
    history.mark_done(7, datetime(2026, 10, 6, 8, 2), "Eze")
    parts["store"].add(42, datetime(2026, 10, 6, 21, 0), "la pastilla", repeat=DAILY, kind=REMINDER)
    parts["store"].add(42, datetime(2026, 10, 7, 7, 0), "mañana no")

    today = board(parts, clock=clock, calendar=both_calendars()).screen()["today"]

    assert [(entry["time"], entry["title"], entry["past"]) for entry in today] == [
        ("08:00", "📌 la pastilla · ✅ Eze", True),
        ("10:00", "<b>Dentista</b>", False),
        ("10:00", "Fútbol", False),
        ("21:00", "📌 la pastilla", False),
    ]
    assert today[1]["color"] == PALETTE[0]


def test_a_finished_google_event_of_today_is_past(parts):
    clock = Clock(datetime(2026, 10, 6, 11, 30))

    today = board(parts, clock=clock, calendar=both_calendars()).screen()["today"]

    assert [entry["past"] for entry in today] == [True, True]


def test_an_all_day_event_of_today_has_no_hour(parts):
    clock = Clock(datetime(2026, 10, 12, 9, 0))

    today = board(parts, clock=clock, calendar=both_calendars()).screen()["today"]

    assert [(entry["time"], entry["title"], entry["past"]) for entry in today] == [
        (None, "Feriado", False),
        (None, "Feriado", False),
    ]


def test_a_broken_calendar_reaches_the_screen_problems(parts):
    calendar = calendar_client(
        {SECRET: ConnectionError(f"404 for url: {SECRET}"), OTHER: ICS_OTHER}, []
    )

    answer = board(parts, calendar=calendar).screen()

    assert answer["problems"] == ["No pude leer el calendario personal."]
    assert "secreto-privado" not in json.dumps(answer)


def test_without_collaborators_the_screen_is_empty_but_answers(parts):
    built = Board(store=parts["store"], history=parts["history"], clock=Clock(), timezone=TZ)

    answer = built.screen()

    assert answer["weather"] is None
    assert answer["lists"] == {}
    assert answer["quiet"] is False
    assert built.events(*WEEK)["calendars"] == []


# --- el ícono del cielo ---


@pytest.mark.parametrize(
    "code, icon",
    [
        (0, "☀️"), (1, "🌤️"), (2, "⛅"), (3, "☁️"), (45, "🌫️"), (48, "🌫️"),
        (51, "🌦️"), (57, "🌦️"), (61, "🌧️"), (67, "🌧️"), (80, "🌦️"), (82, "🌦️"),
        (71, "❄️"), (86, "❄️"), (95, "⛈️"), (99, "⛈️"), (12, "⛅"),
    ],
)
def test_each_sky_code_has_its_icon(code, icon):
    assert sky_icon(code) == icon


def test_the_screen_weather_carries_the_icon(parts):
    answer = board(parts, weather=weather_client([])).screen()

    assert answer["weather"]["icon"] == "🌤️"
    assert answer["weather"]["feels_like"] == 21


# --- lo próximo ---


def test_next_is_the_first_thing_that_has_not_started_yet(parts):
    clock = Clock(datetime(2026, 10, 6, 9, 30))
    parts["store"].add(42, datetime(2026, 10, 6, 9, 0), "ya pasó")
    parts["store"].add(42, datetime(2026, 10, 6, 21, 0), "la pastilla", repeat=DAILY, kind=REMINDER)

    upcoming = board(parts, clock=clock, calendar=both_calendars()).screen()["next"]

    assert upcoming == {
        "title": "<b>Dentista</b>",
        "start": "2026-10-06T10:00:00-03:00",
        "time": "10:00",
        "tomorrow": False,
        "color": PALETTE[0],
        "source": "personal",
    }


def test_next_from_the_house_says_so(parts):
    clock = Clock(datetime(2026, 10, 5, 12, 0))
    parts["store"].add(42, datetime(2026, 10, 5, 18, 0), "la pizza")

    upcoming = board(parts, clock=clock).screen()["next"]

    assert upcoming["title"] == "⏰ la pizza"
    assert upcoming["source"] == "La casa"
    assert upcoming["color"] == KIND_COLORS["alarm"]
    assert upcoming["time"] == "18:00"


def test_an_event_that_already_started_is_not_next(parts):
    clock = Clock(datetime(2026, 10, 6, 10, 30))

    upcoming = board(parts, clock=clock, calendar=both_calendars()).screen()["next"]

    assert upcoming is None


def test_with_nothing_left_today_next_looks_at_tomorrow(parts):
    clock = Clock(datetime(2026, 10, 5, 22, 0))

    upcoming = board(parts, clock=clock, calendar=both_calendars()).screen()["next"]

    assert upcoming["title"] == "<b>Dentista</b>"
    assert upcoming["tomorrow"] is True


def test_an_all_day_event_is_never_next(parts):
    clock = Clock(datetime(2026, 10, 11, 20, 0))

    assert board(parts, clock=clock, calendar=both_calendars()).screen()["next"] is None


def test_without_anything_coming_there_is_no_next(parts):
    assert board(parts).screen()["next"] is None


# --- cómo terminó lo de hoy ---


def test_today_carries_the_bare_title_and_how_it_ended(parts):
    clock = Clock(datetime(2026, 10, 6, 12, 0))
    history = parts["history"]
    history.record(7, 42, REMINDER, DAILY, "la pastilla", datetime(2026, 10, 6, 8, 0))
    history.mark_announced(7)
    history.mark_done(7, datetime(2026, 10, 6, 8, 2), "Eze")
    history.record(8, 42, "alarm", DAILY, "arriba", datetime(2026, 10, 6, 7, 0))
    history.mark_announced(8)
    history.record(9, 42, "alarm", "once", "muda", datetime(2026, 10, 6, 9, 0))
    parts["store"].add(42, datetime(2026, 10, 6, 21, 0), "la basura")

    today = board(parts, clock=clock, calendar=both_calendars()).screen()["today"]

    assert [(entry["label"], entry["mark"]) for entry in today] == [
        ("⏰ arriba", "✓"),
        ("📌 la pastilla", "✓ Eze"),
        ("⏰ muda", "⚠️ no sonó"),
        ("<b>Dentista</b>", ""),
        ("Fútbol", ""),
        ("⏰ la basura", ""),
    ]

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeauto.agenda.ical import Event
from homeauto.agenda.speech import describe

TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def event(hour, minute, summary, all_day=False, location=""):
    start = datetime(2026, 8, 30, hour, minute, tzinfo=TZ)
    return Event(
        uid=f"{summary}@t",
        summary=summary,
        start=start,
        end=start + timedelta(hours=1),
        all_day=all_day,
        calendar="personal",
        location=location,
    )


def test_an_empty_day_says_so():
    text = describe([], label="hoy")

    assert "hoy" in text.lower()
    assert "nada" in text.lower()


def test_one_event_reads_in_singular():
    text = describe([event(10, 0, "Reunión con el equipo")], label="hoy")

    assert "1 cosa" in text or "una cosa" in text.lower()
    assert "Reunión con el equipo" in text


def test_several_events_read_in_plural():
    text = describe([event(10, 0, "Reunión"), event(15, 0, "Dentista")], label="hoy")

    assert "2 cosas" in text or "dos cosas" in text.lower()


def test_times_are_spoken_simply_on_the_hour():
    text = describe([event(10, 0, "Reunión")], label="hoy")

    assert "a las 10" in text.lower()
    assert "10:00" not in text, "en punto no hace falta decir los minutos"


def test_times_with_minutes_keep_them():
    text = describe([event(10, 30, "Reunión")], label="hoy")

    assert "10:30" in text


def test_all_day_events_are_announced_as_such():
    text = describe([event(0, 0, "Feriado", all_day=True)], label="hoy")

    assert "todo el día" in text.lower()
    assert "Feriado" in text


def test_all_day_events_come_first():
    text = describe(
        [event(9, 0, "Reunión"), event(0, 0, "Feriado", all_day=True)],
        label="hoy",
    )

    assert text.index("Feriado") < text.index("Reunión")


def test_the_place_is_mentioned_when_there_is_one():
    text = describe([event(10, 0, "Dentista", location="Consultorio")], label="hoy")

    assert "Consultorio" in text


def test_it_reads_as_a_finished_sentence():
    text = describe([event(10, 0, "Reunión")], label="mañana")

    assert text.endswith(".")
    assert "None" not in text
    assert "mañana" in text.lower()

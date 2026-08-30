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
    # 🔴 Decía "tenés 1 cosa" y el sintetizador leía el dígito como "uno cosa".
    text = describe([event(10, 0, "Reunión con el equipo")], label="hoy")

    assert "una cosa" in text.lower()
    assert "1 cosa" not in text
    assert "Reunión con el equipo" in text


def test_several_events_read_in_plural():
    text = describe([event(10, 0, "Reunión"), event(15, 0, "Dentista")], label="hoy")

    assert "dos cosas" in text.lower()
    assert "2 cosas" not in text


def test_times_are_spoken_simply_on_the_hour():
    text = describe([event(10, 0, "Reunión")], label="hoy")

    assert "a las diez de la mañana" in text.lower()
    assert "10:00" not in text, "en punto no hace falta decir los minutos"


def test_times_with_minutes_keep_them():
    text = describe([event(10, 30, "Reunión")], label="hoy")

    assert "a las diez y media de la mañana" in text.lower()
    assert "10:30" not in text


def test_one_in_the_afternoon_is_feminine_and_singular():
    text = describe([event(13, 0, "Almuerzo")], label="hoy")

    assert "a la una de la tarde" in text.lower()


def test_nothing_we_write_reaches_the_speaker_as_a_digit():
    """Lo que generamos va en palabras; el título del evento se respeta literal."""
    text = describe([event(21, 15, "Cita"), event(9, 0, "Otra")], label="hoy")

    assert not any(character.isdigit() for character in text)


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

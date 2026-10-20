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


def test_an_empty_day_keeps_its_sentence():
    assert describe([], label="mañana") == "No tenés nada agendado mañana."


def test_one_event_is_a_single_sentence():
    text = describe([event(9, 0, "Reunión equipo semanal")], label="mañana")

    assert text == "Mañana a las nueve de la mañana tenés Reunión equipo semanal."


def test_one_event_with_its_place():
    text = describe([event(10, 0, "Dentista", location="Sanatorio X")], label="hoy")

    assert text == "Hoy a las diez de la mañana tenés Dentista, en Sanatorio X."


def test_one_all_day_event():
    text = describe([event(0, 0, "Feria", all_day=True)], label="hoy")

    assert text == "Hoy todo el día tenés Feria."


def test_two_events_are_one_sentence():
    text = describe([event(10, 0, "Reunión"), event(15, 0, "Dentista")], label="hoy")

    assert text == (
        "Hoy tenés dos cosas: a las diez de la mañana, Reunión; "
        "y a las tres de la tarde, Dentista."
    )


def test_three_events_put_all_day_first_and_join_the_last_with_y():
    text = describe(
        [event(11, 0, "Médico"), event(0, 0, "Feria", all_day=True), event(9, 0, "Reunión")],
        label="hoy",
    )

    assert text == (
        "Hoy tenés tres cosas: todo el día, Feria; a las nueve de la mañana, Reunión; "
        "y a las once de la mañana, Médico."
    )


def test_several_events_carry_their_place():
    text = describe(
        [event(9, 0, "Dentista", location="Sanatorio X"), event(11, 0, "Médico")],
        label="mañana",
    )

    assert text == (
        "Mañana tenés dos cosas: a las nueve de la mañana, Dentista, en Sanatorio X; "
        "y a las once de la mañana, Médico."
    )


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


def test_the_summary_leaves_the_place_out():
    """En el resumen de la mañana el lugar sobra: es lo que más lo alargaba.

    Pedido del dueño, escuchándolo: la hora y el título alcanzan. En `/agenda`,
    que se pide a propósito, el lugar sigue estando.
    """
    events = [event(10, 0, "Dentista", location="Sanatorio Colegiales")]

    assert "Sanatorio" not in describe(events, label="hoy", place=False)
    assert "Dentista" in describe(events, label="hoy", place=False)
    assert "diez de la mañana" in describe(events, label="hoy", place=False)


def test_without_a_label_the_sentence_still_starts_well():
    assert describe([event(9, 0, "Reunión")], label="") == (
        "A las nueve de la mañana tenés Reunión."
    )

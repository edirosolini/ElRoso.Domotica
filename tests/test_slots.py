"""Qué le falta a un comando para poder ejecutarse.

Es lo que convierte "creá una alarma" en una pregunta en vez de un error de
parser. La autoridad sigue siendo `timespec`: acá solo se mira si el dato está,
nunca se inventa cuál es.
"""

import pytest

from homeauto import slots


@pytest.mark.parametrize(
    "argument, name",
    [
        ("", "hora"),
        ("en comedor", "hora"),
        ("7:30", "mensaje"),
        ("mañana 8:00", "mensaje"),
        ("diaria", "hora"),
        ("diaria 7:30", "mensaje"),
        ("lun-vie", "hora"),
        ("lun-vie 5:30", "mensaje"),
        ("7:30 arriba", "repeticion"),
    ],
)
def test_what_an_alarm_is_still_missing(argument, name):
    slot = slots.missing("alarma", argument)
    assert slot is not None and slot.name == name


@pytest.mark.parametrize(
    "argument",
    ["diaria 7:30 arriba", "lun-vie 5:30 arriba", "en comedor diaria 7:30 arriba"],
)
def test_an_alarm_that_says_how_it_repeats_is_complete(argument):
    assert slots.missing("alarma", argument) is None


def test_a_one_off_alarm_is_asked_how_it_repeats():
    """El pedido del dueño: preguntar los días, no elegirlos por él."""
    slot = slots.missing("alarma", "7:30 arriba")
    assert slot.name == "repeticion"
    assert "una sola vez" in slot.question.lower()


@pytest.mark.parametrize(
    "argument, name",
    [("", "hora"), ("en comedor", "hora"), ("10m", "mensaje")],
)
def test_what_a_timer_is_still_missing(argument, name):
    slot = slots.missing("timer", argument)
    assert slot is not None and slot.name == name


def test_a_timer_never_asks_how_it_repeats():
    """Un timer es de una vez por definición; preguntarlo sería ruido."""
    assert slots.missing("timer", "10m sacá la pizza") is None


def test_the_delay_question_is_not_the_alarm_one():
    assert slots.missing("timer", "").question != slots.missing("alarma", "").question


@pytest.mark.parametrize("argument", ["", "en comedor", "en todos  "])
def test_saying_nothing_asks_what_to_say(argument):
    assert slots.missing("decir", argument).name == "mensaje"


def test_a_message_to_say_is_complete():
    assert slots.missing("decir", "en comedor que bajen a comer") is None


@pytest.mark.parametrize(
    "command, argument, name",
    [
        ("cancelar", "", "numero"),
        ("cancelar", "el segundo", "numero"),
        ("volumen", "", "volumen"),
        ("volumen", "fuerte", "volumen"),
        ("usar", "", "equipo"),
    ],
)
def test_the_other_commands_that_need_a_datum(command, argument, name):
    assert slots.missing(command, argument).name == name


@pytest.mark.parametrize(
    "command, argument",
    [("cancelar", "3"), ("volumen", "40"), ("usar", "comedor")],
)
def test_those_commands_with_their_datum_are_complete(command, argument):
    assert slots.missing(command, argument) is None


@pytest.mark.parametrize(
    "command",
    ["clima", "lista", "estado", "equipos", "parar", "apagar", "hablar", "silencio", "agenda"],
)
def test_a_command_without_obligatory_data_never_asks(command):
    assert slots.missing(command, "") is None


def test_an_unknown_command_never_asks():
    assert slots.missing("bailar", "") is None


def test_the_question_is_for_the_chat_so_it_may_carry_digits():
    """No se sintetiza: `free_text` contesta al chat, no al parlante."""
    assert "/lista" in slots.missing("cancelar", "").question


@pytest.mark.parametrize(
    "argument",
    ["hola arriba", "mañana", "mañana arriba", "en comedor hola arriba"],
)
def test_something_that_is_not_a_time_still_misses_the_time(argument):
    """No se adivina: si el primer token no es una hora ni una duración, falta."""
    assert slots.missing("alarma", argument).name == "hora"


def test_tomorrow_with_a_clock_only_misses_the_message():
    assert slots.missing("alarma", "mañana 8:00").name == "mensaje"

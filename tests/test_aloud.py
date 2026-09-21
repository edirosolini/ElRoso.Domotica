"""Pedir que algo salga por el parlante, diciéndolo al final del mensaje."""

import pytest

from homeauto.aloud import strip_aloud


@pytest.mark.parametrize(
    "message",
    [
        "cómo viene el clima por el parlante",
        "cómo viene el clima en el parlante",
        "cómo viene el clima en voz alta",
        "cómo viene el clima por los parlantes",
        "cómo viene el clima, decilo por el parlante",
        "cómo viene el clima y reproducilo en el parlante",
        "cómo viene el clima por el parlante.",
        "Cómo viene el clima POR EL PARLANTE",
    ],
)
def test_it_hears_the_request_and_takes_it_out(message):
    aloud, rest = strip_aloud(message)

    assert aloud is True
    assert rest.lower().strip() == "cómo viene el clima"


@pytest.mark.parametrize(
    "message",
    [
        "cómo viene el clima",
        "poneme una alarma a las siete",
        "decile a Diego que baje",
        "qué parlante tengo",
        "el parlante del comedor anda mal",
    ],
)
def test_a_message_that_does_not_ask_for_it_is_left_alone(message):
    aloud, rest = strip_aloud(message)

    assert aloud is False
    assert rest == message


def test_asking_for_it_and_nothing_else_leaves_no_text():
    aloud, rest = strip_aloud("por el parlante")

    assert aloud is True
    assert rest == ""

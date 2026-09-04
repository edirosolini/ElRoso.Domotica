"""La frase con la que la casa llama a alguien.

La escribe la casa, no la persona: "llamar a todos a cenar" no trae las palabras
que hay que decir, trae la intención. Por eso esto genera texto —y por eso pasa
por el pulidor— en vez de recortar el mensaje.
"""

from datetime import datetime

import pytest

from homeauto.summon import phrase

NIGHT = datetime(2026, 9, 4, 21, 30)
NOON = datetime(2026, 9, 4, 13, 0)
MORNING = datetime(2026, 9, 4, 8, 0)
AFTERNOON = datetime(2026, 9, 4, 17, 0)


@pytest.mark.parametrize("what", ["a cenar", "cenar", "  a cenar  "])
def test_it_calls_people_to_what_was_asked(what):
    assert phrase(what, NIGHT) == "Vengan a cenar."


def test_a_generic_meal_follows_the_clock():
    """«a comer» no dice qué comida; la hora sí."""
    assert phrase("a comer", NIGHT) == "Vengan a cenar."
    assert phrase("a comer", NOON) == "Vengan a almorzar."
    assert phrase("a comer", MORNING) == "Vengan a desayunar."
    assert phrase("a comer", AFTERNOON) == "Vengan a merendar."


def test_without_anything_it_calls_to_the_meal_of_the_hour():
    assert phrase("", NIGHT) == "Vengan a cenar."


def test_the_meal_word_alone_also_counts():
    assert phrase("la comida", NOON) == "Vengan a almorzar."


def test_anything_else_is_kept_as_it_came():
    assert phrase("a la mesa", NIGHT) == "Vengan a la mesa."
    assert phrase("tomar la merienda", AFTERNOON) == "Vengan a tomar la merienda."


def test_it_ends_in_one_period():
    assert phrase("a cenar.", NIGHT) == "Vengan a cenar."
    assert phrase("a cenar!", NIGHT) == "Vengan a cenar."


def test_it_never_carries_a_digit_of_its_own():
    """Lo que genera la casa se sintetiza: un dígito ahí se lee mal."""
    assert not any(char.isdigit() for char in phrase("", NIGHT))

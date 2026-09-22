"""Cuentas y conversiones, resueltas acá y no por un modelo."""

import pytest

from homeauto.calc import CalcError, evaluate


def said(text):
    return evaluate(text).spoken


def written(text):
    return evaluate(text).written


# --- aritmética -------------------------------------------------------------


def test_a_plain_multiplication():
    result = evaluate("15 * 4")

    assert "60" in result.written
    assert "sesenta" in result.spoken


def test_the_words_people_use_are_operators():
    assert "60" in written("cuánto es 15 por 4")
    assert "19" in written("15 más 4")
    assert "11" in written("15 menos 4")
    assert "5" in written("15 dividido 3")


def test_a_decimal_result_is_said_with_a_comma():
    """Escrito con coma, Piper lee dos números sueltos: va en palabras."""
    result = evaluate("10 / 4")

    assert "2,5" in result.written
    assert "dos coma cinco" in result.spoken


def test_a_decimal_is_written_the_way_it_is_typed():
    assert "4,5" in written("1,5 * 3")


def test_percentages():
    result = evaluate("15% de 200")

    assert "30" in result.written
    assert "treinta" in result.spoken


def test_parentheses_and_powers():
    assert "20" in written("(2 + 3) * 4")
    assert "8" in written("2 ** 3")


def test_dividing_by_zero_is_explained():
    with pytest.raises(CalcError, match="cero"):
        evaluate("5 / 0")


def test_something_that_is_not_a_calculation_is_rejected():
    with pytest.raises(CalcError):
        evaluate("qué hora es")


def test_nothing_gets_executed():
    """El evaluador acepta aritmética y nada más."""
    for attack in ("__import__('os').system('ls')", "open('/etc/passwd')", "1 if x else 2"):
        with pytest.raises(CalcError):
            evaluate(attack)


def test_an_absurd_power_is_refused_instead_of_hanging():
    """Restricción del evaluador: 9**9**9 cuelga el proceso antes de contestar."""
    with pytest.raises(CalcError):
        evaluate("9 ** 9 ** 9")


# --- unidades ---------------------------------------------------------------


def test_temperature_between_celsius_and_fahrenheit():
    result = evaluate("20 grados en fahrenheit")

    assert "68" in result.written
    assert "sesenta y ocho" in result.spoken
    assert "fahrenheit" in result.spoken.lower()


def test_length():
    result = evaluate("5 km en millas")

    assert "3,11" in result.written
    assert "tres coma once" in result.spoken
    assert "millas" in result.spoken


def test_weight():
    assert "2,2" in written("1 kg en libras")


def test_volume():
    assert "litro" in said("1 galón en litros").lower()


def test_the_plural_follows_the_number():
    assert "un kilómetro" in said("1000 metros en kilómetros")


def test_units_of_different_kinds_do_not_convert():
    with pytest.raises(CalcError, match="no se convierte"):
        evaluate("5 km en litros")


def test_an_unknown_unit_is_named_in_the_error():
    with pytest.raises(CalcError, match="cuarterones"):
        evaluate("5 cuarterones en litros")


# --- lo que no se puede decir ----------------------------------------------


def test_a_result_too_big_to_say_is_still_written():
    """`verbalize` corta en 999.999: se escribe igual, pero no se habla."""
    result = evaluate("999999 * 99")

    assert result.written
    assert result.spoken == ""


def test_no_digit_survives_in_what_gets_spoken():
    for text in ("15 * 4", "10 / 4", "20 grados en fahrenheit", "5 km en millas"):
        assert not any(character.isdigit() for character in evaluate(text).spoken), text


def test_the_typed_decimal_comma_survives_in_writing():
    """Se escribe como lo escribió la persona, no como lo lee Python."""
    assert written("1,5 * 3").startswith("1,5")


def test_a_unit_without_an_abbreviation_is_written_in_words():
    assert "2 tazas" in written("2 tazas en ml")
    assert "1 taza" in written("1 taza en ml")

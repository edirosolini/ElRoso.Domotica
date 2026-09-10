"""Numbers and clock times as a person would say them out loud."""

import pytest

from homeauto.verbalize import FEMININE, clock, decimal, number


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, "cero"),
        (2, "dos"),
        (9, "nueve"),
        (10, "diez"),
        (15, "quince"),
        (16, "dieciséis"),
        (20, "veinte"),
        (22, "veintidós"),
        (30, "treinta"),
        (35, "treinta y cinco"),
        (100, "cien"),
        (101, "ciento un"),
        (115, "ciento quince"),
        (200, "doscientos"),
        (543, "quinientos cuarenta y tres"),
        (999, "novecientos noventa y nueve"),
    ],
)
def test_numbers_become_words(value, expected):
    assert number(value) == expected


def test_one_agrees_in_gender():
    # 🔴 El bug real: "tenés 1 cosa" sonaba "tenés uno cosa".
    assert number(1, gender="f") == "una"
    assert number(1) == "un"


def test_twenty_one_agrees_too():
    assert number(21, gender="f") == "veintiuna"
    assert number(21) == "veintiún"


def test_thirty_one_agrees_as_two_words():
    assert number(31, gender="f") == "treinta y una"
    assert number(31) == "treinta y un"


def test_gender_only_touches_the_ones():
    assert number(2, gender="f") == "dos"
    assert number(20, gender="f") == "veinte"


def test_negative_numbers_are_spoken_as_such():
    assert number(-3) == "menos tres"


@pytest.mark.parametrize(
    "hour, minute, expected",
    [
        (1, 0, "la una de la madrugada"),
        (13, 0, "la una de la tarde"),
        (10, 0, "las diez de la mañana"),
        (21, 0, "las nueve de la noche"),
        (0, 0, "las doce de la noche"),
        (12, 0, "las doce del mediodía"),
        (10, 30, "las diez y media de la mañana"),
        (10, 15, "las diez y cuarto de la mañana"),
        (21, 45, "las nueve y cuarenta y cinco de la noche"),
        (13, 1, "la una y un minuto de la tarde"),
    ],
)
def test_clock_times_read_like_speech(hour, minute, expected):
    assert clock(hour, minute) == expected


def test_no_digit_survives():
    """Whatever comes out must be sayable: a digit would be read wrong."""
    for hour in range(24):
        for minute in (0, 1, 15, 30, 45, 59):
            assert not any(character.isdigit() for character in clock(hour, minute))
    for value in range(-50, 1000):
        assert not any(character.isdigit() for character in number(value))


def test_a_number_too_big_to_say_is_rejected():
    """Mejor fallar que colar un dígito en el audio sin que nadie lo note."""
    with pytest.raises(ValueError):
        number(1_000_000)
    with pytest.raises(ValueError):
        number(-1_000_000)


@pytest.mark.parametrize("hour, minute", [(24, 0), (-1, 0), (0, 60), (0, -1)])
def test_an_impossible_time_is_rejected(hour, minute):
    with pytest.raises(ValueError):
        clock(hour, minute)


# --- miles y decimales ------------------------------------------------------


@pytest.mark.parametrize(
    "value, said",
    [
        (1000, "mil"),
        (1001, "mil un"),
        (1535, "mil quinientos treinta y cinco"),
        (1521, "mil quinientos veintiún"),
        (2000, "dos mil"),
        (15000, "quince mil"),
        (21000, "veintiún mil"),
        (100000, "cien mil"),
        (999999, "novecientos noventa y nueve mil novecientos noventa y nueve"),
    ],
)
def test_thousands_are_said_as_words(value, said):
    """🔴 El dólar no entra en tres cifras.

    `number(1545)` tiraba ValueError, así que ninguna cifra de plata podía
    llegar al parlante: es lo que frenaba el resumen económico.
    """
    assert number(value) == said


def test_a_thousand_agrees_with_what_it_counts():
    assert number(1200, FEMININE) == "mil doscientas"
    assert number(21000, FEMININE) == "veintiún mil", "el mil manda, y mil es masculino"


def test_past_the_millions_it_still_refuses():
    with pytest.raises(ValueError):
        number(1_000_000)


@pytest.mark.parametrize(
    "value, said",
    [
        (2.1, "dos coma uno"),
        (0.5, "cero coma cinco"),
        (-1.4, "menos uno coma cuatro"),
        (12.35, "doce coma treinta y cinco"),
        (3.0, "tres"),
    ],
)
def test_decimals_are_said_with_the_comma(value, said):
    """La inflación es un decimal, y "2,1" se lee "dos uno" sin la coma."""
    assert decimal(value) == said


def test_a_decimal_counts_things_too():
    assert decimal(1.5, FEMININE) == "una coma cinco"

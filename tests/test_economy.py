"""Los tres números de la economía que la casa dice a la mañana."""

import pytest

from homeauto.economy import EconomyClient, EconomyError

DOLLAR = {"casa": "oficial", "compra": 1485, "venta": 1535,
          "fechaActualizacion": "2026-09-10T13:00:00.000Z"}
RISK = {"valor": 491, "fecha": "2026-09-09"}
INFLATION = [
    {"fecha": "2026-06-30", "valor": 1.9},
    {"fecha": "2026-07-31", "valor": 2.1},
]


def fetcher(**payloads):
    """Un doble por URL, para que una fuente pueda romperse sola."""
    def fetch(url):
        for fragment, payload in payloads.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"nadie pidió {url}")

    return fetch


def everything():
    return fetcher(dolares=DOLLAR, **{"riesgo-pais": RISK, "inflacion": INFLATION})


def test_the_dollar_is_said_at_its_selling_price():
    money = EconomyClient(fetch=everything())

    assert money.dollar() == 1535


def test_the_three_figures_are_said_in_words():
    said = EconomyClient(fetch=everything()).spoken()

    assert "mil quinientos treinta y cinco pesos" in said
    assert "cuatrocientos noventa y un" in said
    assert "dos coma uno por ciento" in said
    assert "julio" in said


def test_nothing_spoken_carries_a_digit():
    """🔴 Lo mismo que la agenda y el clima: un dígito lo lee mal el parlante."""
    said = EconomyClient(fetch=everything()).spoken()

    assert not any(character.isdigit() for character in said), said


def test_a_source_that_fails_leaves_the_others_standing():
    """Cada número es independiente: el dólar caído no cuesta la inflación."""
    money = EconomyClient(
        fetch=fetcher(
            dolares=EconomyError("no contesta"),
            **{"riesgo-pais": RISK, "inflacion": INFLATION},
        )
    )

    said = money.spoken()

    assert "dólar" not in said.lower()
    assert "cuatrocientos noventa y un" in said
    assert "dos coma uno por ciento" in said


def test_everything_down_says_nothing_at_all():
    """Sin ningún dato, el resumen no gana un renglón que no dice nada."""
    money = EconomyClient(
        fetch=fetcher(
            dolares=EconomyError("no"),
            **{"riesgo-pais": EconomyError("no"), "inflacion": EconomyError("no")},
        )
    )

    assert money.spoken() == ""


def test_the_inflation_is_the_last_month_of_the_series():
    money = EconomyClient(fetch=everything())

    month, value = money.inflation()

    assert (month, value) == ("julio", 2.1)


def test_an_answer_that_makes_no_sense_is_not_said():
    money = EconomyClient(fetch=fetcher(dolares={"algo": "raro"},
                                        **{"riesgo-pais": RISK, "inflacion": INFLATION}))

    with pytest.raises(EconomyError):
        money.dollar()
    assert "dólar" not in money.spoken().lower()


def test_a_figure_too_big_to_say_is_dropped_instead_of_spoken_with_digits():
    """🔴 Si algún día el dólar pasa el millón, se calla: nunca sale un dígito."""
    money = EconomyClient(
        fetch=fetcher(
            dolares={"venta": 1_500_000},
            **{"riesgo-pais": RISK, "inflacion": INFLATION},
        )
    )

    said = money.spoken()

    assert "dólar" not in said.lower()
    assert not any(character.isdigit() for character in said)

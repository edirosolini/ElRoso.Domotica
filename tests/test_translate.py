"""Traducir: texto para leer, nunca para decir."""

import pytest

from homeauto.translate import MAX_TEXT, TranslateError, Translator


def model(answer="hello", boom=None, seen=None):
    def call(prompt):
        if seen is not None:
            seen.append(prompt)
        if boom:
            raise boom
        return answer

    return call


def test_it_returns_what_the_model_answered():
    assert Translator(model("hello")).translate("hola") == "hello"


def test_the_text_travels_whole():
    seen = []
    Translator(model(seen=seen)).translate("hola qué tal")

    assert "hola qué tal" in seen[0]


def test_without_a_language_it_goes_between_spanish_and_english():
    """El caso de esta casa: lo que está en español sale en inglés y al revés."""
    seen = []
    Translator(model(seen=seen)).translate("hola")

    assert "inglés" in seen[0] and "español" in seen[0]


def test_the_language_can_be_named_up_front():
    seen = []
    Translator(model("bonjour", seen=seen)).translate("al francés hola")

    assert "francés" in seen[0]
    assert "al francés" not in seen[0].split("Texto:")[-1], "el prefijo no se traduce"


def test_only_a_known_language_is_treated_as_one():
    """Un prefijo que también puede ser texto se come parte del mensaje."""
    seen = []
    Translator(model(seen=seen)).translate("al final no fui")

    assert "al final no fui" in seen[0].split("Texto:")[-1]


def test_a_model_that_fails_is_reported():
    with pytest.raises(TranslateError):
        Translator(model(boom=RuntimeError("sin red"))).translate("hola")


def test_an_empty_answer_is_refused():
    with pytest.raises(TranslateError):
        Translator(model("   ")).translate("hola")


def test_an_answer_that_ran_away_is_refused():
    """Una traducción no es un ensayo: si creció así, no es una traducción."""
    with pytest.raises(TranslateError):
        Translator(model("palabra " * 200)).translate("hola")


def test_a_text_too_long_never_reaches_the_model():
    seen = []
    with pytest.raises(TranslateError, match="largo"):
        Translator(model(seen=seen)).translate("x" * (MAX_TEXT + 1))

    assert seen == [], "ni se pregunta"


def test_nothing_to_translate_is_refused():
    with pytest.raises(TranslateError):
        Translator(model()).translate("   ")


def test_the_same_text_is_asked_only_once():
    seen = []
    translator = Translator(model(seen=seen))

    translator.translate("hola")
    translator.translate("hola")

    assert len(seen) == 1


def test_the_language_is_part_of_the_cache_key():
    seen = []
    translator = Translator(model(seen=seen))

    translator.translate("hola")
    translator.translate("al francés hola")

    assert len(seen) == 2


def test_surrounding_quotes_are_dropped():
    assert Translator(model('"hello"')).translate("hola") == "hello"

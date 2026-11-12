"""El nombre en castellano de cada equipo y la búsqueda de un alias por cómo se escribió."""

import pytest

from homeauto.voice.names import device_label, find_alias, fold


@pytest.mark.parametrize("alias, label", [
    ("recamara", "Recámara"),
    ("habitacion", "Habitación"),
    ("comedor", "Comedor"),
    ("living", "Living"),
    ("cocina", "Cocina"),
    ("bano", "Baño"),
    ("jardin", "Jardín"),
    ("estudio", "Estudio"),
    ("oficina", "Oficina"),
    ("dormitorio", "Dormitorio"),
    ("cuarto", "Cuarto"),
    ("patio", "Patio"),
    ("quincho", "Quincho"),
    ("sala", "Sala"),
])
def test_a_known_room_gets_its_spanish_name(alias, label):
    assert device_label(alias) == label


def test_an_underscore_is_a_space_between_known_words():
    assert device_label("sala_de_estar") == "Sala de estar"
    assert device_label("bano_principal") == "Baño principal"


def test_an_unknown_alias_only_gets_spaces_and_a_capital():
    assert device_label("tele_chica") == "Tele chica"
    assert device_label("nest2") == "Nest2"


def test_fold_drops_accents_and_case():
    assert fold("RECÁMARA") == "recamara"
    assert fold("Baño") == "bano"


@pytest.mark.parametrize("written", ["Recámara", "RECAMARA", "recámara", "recamara", " Recámara "])
def test_find_alias_matches_however_it_was_written(written):
    assert find_alias(written, ["comedor", "recamara"]) == "recamara"


def test_find_alias_matches_the_label_with_spaces():
    assert find_alias("Sala de estar", ["sala_de_estar"]) == "sala_de_estar"


def test_find_alias_of_something_unknown_is_none():
    assert find_alias("casa", ["comedor", "recamara"]) is None

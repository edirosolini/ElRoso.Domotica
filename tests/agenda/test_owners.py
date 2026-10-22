"""De quién es un evento de Google: por el prefijo del título o por el calendario."""

import pytest

from homeauto.agenda.owners import calendar_owner, owners

NAMES = {1: "Papá", 2: "Mamá", 3: "China"}


@pytest.mark.parametrize(
    "title",
    ["[Papá] Dentista", "[papa] Dentista", "[PAPÁ] Dentista", " [Papá] Dentista",
     "[Papá]Dentista"],
)
def test_a_prefix_of_the_padron_names_the_owner(title):
    assert owners(title, NAMES) == ((1,), ("Papá",), "Dentista")


@pytest.mark.parametrize("title", ["[Papá][Mamá] Cena", "[Papá] [Mamá] Cena"])
def test_several_prefixes_name_several_owners(title):
    assert owners(title, NAMES) == ((1, 2), ("Papá", "Mamá"), "Cena")


def test_owners_come_without_repeating_in_order():
    assert owners("[Mamá][papa][Mamá] Cena", NAMES) == ((2, 1), ("Mamá", "Papá"), "Cena")


@pytest.mark.parametrize(
    "title",
    ["[Eze] Dentista", "Dentista [Papá]", "[] Dentista", "[Papá Dentista",
     "[Papá1] Dentista", "[Papá][Eze] Dentista", "Dentista"],
)
def test_what_is_not_all_from_the_padron_stays_literal(title):
    assert owners(title, NAMES) == ((), (), title)


def test_an_empty_padron_leaves_the_title_literal():
    assert owners("[Papá] Dentista", {}) == ((), (), "[Papá] Dentista")


def test_todos_is_for_everyone():
    assert owners("[Todos] Asado", NAMES) == ((), ("todos",), "Asado")


def test_a_title_that_is_only_the_prefix_has_nothing_left():
    assert owners("[Papá]", NAMES) == ((1,), ("Papá",), "")


def test_a_folding_clash_counts_for_both():
    names = {4: "José", 5: "Jose"}

    assert owners("[jose] Turno", names) == ((4, 5), ("José", "Jose"), "Turno")


def test_a_calendar_named_after_a_person_is_hers():
    assert calendar_owner("papa", NAMES) == ((1,), ("Papá",))


@pytest.mark.parametrize("alias", ["familia", "familia_privado", "personal"])
def test_a_calendar_that_is_not_a_person_is_for_everyone(alias):
    assert calendar_owner(alias, NAMES) == ((), ())

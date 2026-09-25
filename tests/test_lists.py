"""Las listas de la casa: qué comprar y qué hacer."""

import pytest

from homeauto.lists import ListError, ListStore, SHOPPING, TODO, resolve


@pytest.fixture
def store(tmp_path):
    return ListStore(tmp_path / "jobs.db")


def test_what_gets_added_comes_back_in_order(store):
    store.add(SHOPPING, ["leche", "pan"])
    store.add(SHOPPING, ["yerba"])

    assert store.items(SHOPPING) == ["leche", "pan", "yerba"]


def test_the_lists_do_not_mix(store):
    store.add(SHOPPING, ["leche"])
    store.add(TODO, ["llamar al plomero"])

    assert store.items(SHOPPING) == ["leche"]
    assert store.items(TODO) == ["llamar al plomero"]


def test_something_already_there_is_not_added_twice(store):
    store.add(SHOPPING, ["leche"])

    added = store.add(SHOPPING, ["Leche", "pan"])

    assert added == ["pan"], "el duplicado no entra ni cambia de mayúsculas"
    assert store.items(SHOPPING) == ["leche", "pan"]


def test_an_item_is_removed_by_its_position(store):
    store.add(SHOPPING, ["leche", "pan", "yerba"])

    removed = store.remove(SHOPPING, 2)

    assert removed == "pan"
    assert store.items(SHOPPING) == ["leche", "yerba"]


def test_removing_what_is_not_there_says_so(store):
    store.add(SHOPPING, ["leche"])

    assert store.remove(SHOPPING, 7) is None


def test_the_whole_list_can_be_emptied(store):
    store.add(SHOPPING, ["leche", "pan"])

    assert store.clear(SHOPPING) == 2
    assert store.items(SHOPPING) == []


def test_an_empty_list_is_not_an_error(store):
    assert store.items(SHOPPING) == []


def test_the_store_survives_being_reopened(tmp_path):
    ListStore(tmp_path / "jobs.db").add(SHOPPING, ["leche"])

    assert ListStore(tmp_path / "jobs.db").items(SHOPPING) == ["leche"]


def test_nothing_useful_is_added(store):
    assert store.add(SHOPPING, ["", "   "]) == []


# --- cómo se nombra una lista ----------------------------------------------


def test_the_names_people_use(store):
    assert resolve("compras") == SHOPPING
    assert resolve("la lista de compras") == SHOPPING
    assert resolve("pendientes") == TODO
    assert resolve("tareas") == TODO


def test_an_unknown_list_is_named_in_the_error():
    with pytest.raises(ListError, match="ferretería"):
        resolve("ferretería")


def test_entries_carry_an_id_that_does_not_move(store):
    store.add(SHOPPING, ["leche", "pan"])
    before = dict(store.entries(SHOPPING))

    store.remove(SHOPPING, 1)

    assert store.entries(SHOPPING) == [(next(k for k, v in before.items() if v == "pan"), "pan")]


def test_an_item_is_removed_by_its_id(store):
    store.add(SHOPPING, ["leche", "pan"])
    pan = store.entries(SHOPPING)[1][0]

    assert store.remove_id(SHOPPING, pan) == "pan"
    assert store.items(SHOPPING) == ["leche"]


def test_an_id_from_another_list_is_not_removed(store):
    store.add(SHOPPING, ["leche"])
    leche = store.entries(SHOPPING)[0][0]

    assert store.remove_id(TODO, leche) is None
    assert store.items(SHOPPING) == ["leche"]


def test_an_id_that_is_gone_says_so(store):
    assert store.remove_id(SHOPPING, 999) is None

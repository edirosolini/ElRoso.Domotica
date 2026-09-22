"""`/agregar`, `/compras`, `/pendientes` y `/sacar`: las listas desde el chat."""

import pytest

from homeauto.bot.commands import Commands
from homeauto.lists import SHOPPING, TODO, ListStore

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42


@pytest.fixture
def cmd(tmp_path):
    return Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        lists=ListStore(tmp_path / "jobs.db"),
    )


def test_adding_goes_to_the_shopping_list(cmd):
    reply = cmd.add_item(OWNER, "leche")

    assert "leche" in reply
    assert cmd.lists.items(SHOPPING) == ["leche"]


def test_several_items_at_once(cmd):
    cmd.add_item(OWNER, "leche, pan y yerba")

    assert cmd.lists.items(SHOPPING) == ["leche", "pan", "yerba"]


def test_the_other_list_is_named_up_front(cmd):
    cmd.add_item(OWNER, "a pendientes llamar al plomero")

    assert cmd.lists.items(TODO) == ["llamar al plomero"]
    assert cmd.lists.items(SHOPPING) == []


def test_a_list_that_is_named_the_long_way(cmd):
    cmd.add_item(OWNER, "a la lista de compras detergente")

    assert cmd.lists.items(SHOPPING) == ["detergente"]


def test_something_that_only_looks_like_a_list_name_is_an_item(cmd):
    """"a comprar pan" no nombra una lista: es lo que hay que comprar."""
    cmd.add_item(OWNER, "a comprar pan")

    assert cmd.lists.items(SHOPPING) == ["a comprar pan"]


def test_a_duplicate_is_reported_not_repeated(cmd):
    cmd.add_item(OWNER, "leche")

    reply = cmd.add_item(OWNER, "leche")

    assert cmd.lists.items(SHOPPING) == ["leche"]
    assert "ya" in reply.lower()


def test_adding_nothing_says_how_to_use_it(cmd):
    assert "/agregar" in cmd.add_item(OWNER, "")


def test_the_shopping_list_comes_back_numbered(cmd):
    cmd.add_item(OWNER, "leche, pan")

    reply = cmd.shopping(OWNER)

    assert "1. leche" in reply
    assert "2. pan" in reply


def test_the_list_says_how_to_remove_an_item(cmd):
    """Como /lista con /cancelar: quien ve la lista lee cómo borrar de ahí."""
    cmd.add_item(OWNER, "leche")

    assert "/sacar" in cmd.shopping(OWNER)


def test_an_empty_list_says_it_is_empty(cmd):
    assert "vacía" in cmd.shopping(OWNER).lower()


def test_the_two_lists_are_shown_apart(cmd):
    cmd.add_item(OWNER, "leche")
    cmd.add_item(OWNER, "a pendientes pagar la luz")

    assert "leche" in cmd.shopping(OWNER)
    assert "leche" not in cmd.todo(OWNER)
    assert "pagar la luz" in cmd.todo(OWNER)


def test_removing_by_number(cmd):
    cmd.add_item(OWNER, "leche, pan")

    reply = cmd.remove_item(OWNER, "1")

    assert "leche" in reply
    assert cmd.lists.items(SHOPPING) == ["pan"]


def test_removing_from_the_other_list(cmd):
    cmd.add_item(OWNER, "a pendientes pagar la luz")

    cmd.remove_item(OWNER, "1 de pendientes")

    assert cmd.lists.items(TODO) == []


def test_removing_a_number_that_is_not_there(cmd):
    cmd.add_item(OWNER, "leche")

    reply = cmd.remove_item(OWNER, "7")

    assert "7" in reply
    assert cmd.lists.items(SHOPPING) == ["leche"]


def test_emptying_the_whole_list(cmd):
    cmd.add_item(OWNER, "leche, pan")

    reply = cmd.remove_item(OWNER, "todo")

    assert "2" in reply
    assert cmd.lists.items(SHOPPING) == []


def test_removing_without_a_number_says_how(cmd):
    assert "/sacar" in cmd.remove_item(OWNER, "")


def test_an_unknown_list_is_explained(cmd):
    reply = cmd.add_item(OWNER, "a la lista de ferretería un martillo")

    assert "martillo" in cmd.lists.items(SHOPPING)[0], "lo desconocido no nombra una lista"


def test_without_a_store_it_says_it_is_not_set_up():
    cmd = Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
    )

    assert "listas" in cmd.add_item(OWNER, "leche").lower()
    assert "listas" in cmd.shopping(OWNER).lower()


def test_a_stranger_gets_nothing(cmd):
    assert "lista" in cmd.add_item(999, "leche").lower()
    assert cmd.lists.items(SHOPPING) == []

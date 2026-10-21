"""El padrón de la casa: personas con nombre decible y, si tienen, su chat."""

import sqlite3

import pytest

from homeauto.people import (
    Household, PeopleStore, Person, PersonError, PersonNotFound, PersonStore, Roster,
)

HOUSE = (42, 77, 99)


@pytest.fixture
def db(tmp_path):
    return tmp_path / "jobs.db"


def make(db, chat_ids=HOUSE, before_remove=None):
    return Household(PersonStore(db), chat_ids, before_remove=before_remove)


# --- alta, cambio y baja ---


def test_a_person_is_added_with_or_without_a_chat(db):
    house = make(db)

    eze = house.add("Eze", 42)
    abu = house.add("Abuela")

    assert eze == Person(eze.id, "Eze", 42)
    assert abu == Person(abu.id, "Abuela", None)
    assert house.list() == [abu, eze]


def test_the_padron_survives_a_restart(db):
    eze = make(db).add("Eze", 42)

    assert make(db).list() == [eze]


def test_the_spaces_of_a_name_are_tidied(db):
    assert make(db).add("  Tía   Marta ").name == "Tía Marta"


def test_renaming_keeps_the_id(db):
    house = make(db)
    eze = house.add("Eze", 42)

    renamed = house.rename(eze.id, "Ezequiel")

    assert renamed == Person(eze.id, "Ezequiel", 42)
    assert house.get(eze.id) == renamed


def test_a_chat_is_associated_and_dissociated(db):
    house = make(db)
    abu = house.add("Abuela")

    assert house.set_chat(abu.id, 77) == Person(abu.id, "Abuela", 77)
    assert house.set_chat(abu.id, None) == Person(abu.id, "Abuela", None)


def test_update_changes_name_and_chat_at_once_or_nothing(db):
    house = make(db)
    house.add("Eze", 42)
    abu = house.add("Abuela")

    with pytest.raises(PersonError):
        house.update(abu.id, name="Nona", chat_id=42)
    assert house.get(abu.id) == abu

    assert house.update(abu.id, name="Nona", chat_id=77) == Person(abu.id, "Nona", 77)


def test_removing_deletes_and_returns_who_it_was(db):
    house = make(db)
    eze = house.add("Eze", 42)

    assert house.remove(eze.id) == eze
    assert house.list() == []
    assert house.get(eze.id) is None


def test_removing_calls_the_hook_before_deleting(db):
    seen = []
    house = make(db, before_remove=lambda person: seen.append((person, house.get(person.id))))
    eze = house.add("Eze", 42)

    house.remove(eze.id)

    assert seen == [(eze, eze)]


def test_a_new_id_never_reuses_a_removed_one(db):
    house = make(db)
    first = house.add("Eze")
    house.remove(first.id)

    assert house.add("Diego").id > first.id


@pytest.mark.parametrize("action", ["rename", "set_chat", "remove"])
def test_a_person_that_does_not_exist_is_not_found(db, action):
    house = make(db)
    args = {"rename": ("Eze",), "set_chat": (42,), "remove": ()}[action]

    with pytest.raises(PersonNotFound):
        getattr(house, action)(17, *args)


# --- validaciones ---


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("", "Falta el nombre."),
        ("   ", "Falta el nombre."),
        (None, "Falta el nombre."),
        ("a" * 41, "El nombre no puede pasar de 40 caracteres."),
        ("Eze2", "«Eze2» no se puede decir en voz alta: un nombre va sin números ni guiones."),
        ("Ana-María", "«Ana-María» no se puede decir en voz alta: un nombre va sin números ni guiones."),
        ("todos", "«todos» está reservado: elegí otro nombre."),
        ("Nadie", "«Nadie» está reservado: elegí otro nombre."),
    ],
)
def test_a_name_that_cannot_be_said_is_refused(db, name, reason):
    with pytest.raises(PersonError) as caught:
        make(db).add(name)

    assert str(caught.value) == reason


def test_a_name_of_forty_letters_fits(db):
    assert make(db).add("a" * 40).name == "a" * 40


@pytest.mark.parametrize("other", ["eze", "EZE", " Eze "])
def test_a_name_is_unique_regardless_of_case(db, other):
    house = make(db)
    house.add("Eze")

    with pytest.raises(PersonError) as caught:
        house.add(other)

    assert str(caught.value) == "Ya hay alguien que se llama Eze."


def test_accents_count_for_uniqueness_regardless_of_case(db):
    house = make(db)
    house.add("Ángel")

    with pytest.raises(PersonError):
        house.add("ángel")


def test_renaming_to_its_own_name_in_other_case_is_fine(db):
    house = make(db)
    eze = house.add("Eze")

    assert house.rename(eze.id, "EZE").name == "EZE"


@pytest.mark.parametrize("chat_id", [13, "42", True, 4.2])
def test_a_chat_outside_the_house_is_refused(db, chat_id):
    with pytest.raises(PersonError) as caught:
        make(db).add("Eze", chat_id)

    assert str(caught.value) == "Ese chat no es de la casa."


def test_a_chat_taken_by_someone_else_is_refused(db):
    house = make(db)
    house.add("Eze", 42)

    with pytest.raises(PersonError) as caught:
        house.add("Diego", 42)

    assert str(caught.value) == "Ese chat ya es de Eze."


def test_keeping_its_own_chat_is_fine(db):
    house = make(db)
    eze = house.add("Eze", 42)

    assert house.set_chat(eze.id, 42).chat_id == 42


# --- un chat que salió de ALLOWED_CHAT_IDS ---


def test_a_chat_that_left_the_house_reads_as_no_telegram(db):
    eze = make(db).add("Eze", 42)

    house = make(db, chat_ids=(77,))

    assert house.list() == [Person(eze.id, "Eze", None)]
    assert house.get(eze.id) == Person(eze.id, "Eze", None)
    assert house.by_chat(42) is None


def test_a_chat_that_comes_back_is_its_owner_again(db):
    eze = make(db).add("Eze", 42)
    make(db, chat_ids=(77,))

    assert make(db).by_chat(42) == eze


# --- quién es quién ---


def test_by_chat_finds_the_person_of_that_chat(db):
    house = make(db)
    eze = house.add("Eze", 42)

    assert house.by_chat(42) == eze
    assert house.by_chat(77) is None


def test_the_roster_has_every_person_and_every_chat_of_the_house(db):
    house = make(db, chat_ids=(42, 77))
    eze = house.add("Eze", 42)
    abu = house.add("Abuela")

    assert house.roster() == Roster(person_ids=frozenset({eze.id, abu.id}),
                                    chats=frozenset({42, 77}))


def test_an_empty_padron_falls_back_to_the_chats_of_today(db):
    house = make(db, chat_ids=(42, 77))

    assert house.list() == []
    assert house.roster() == Roster(person_ids=frozenset(), chats=frozenset({42, 77}))


def test_the_padron_is_not_seeded_by_itself(db):
    make(db).roster()

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM persons").fetchone() == (0,)


def test_the_names_seen_in_telegram_stay_apart(db):
    seen = PeopleStore(db)
    seen.remember(42, "Ezequiel Di Rosolini")
    make(db).add("Eze", 42)

    assert seen.names() == {42: "Ezequiel Di Rosolini"}

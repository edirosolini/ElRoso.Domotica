from homeauto.people import People, PeopleStore, display_name


def test_only_the_chats_of_the_house_are_remembered(tmp_path):
    store = PeopleStore(tmp_path / "jobs.db")
    people = People(store, chat_ids=(42,))

    people.meet(42, "Eze")
    people.meet(99, "Un desconocido")

    assert store.names() == {42: "Eze"}


def test_a_name_is_remembered_and_survives_a_restart(tmp_path):
    path = tmp_path / "jobs.db"
    PeopleStore(path).remember(42, "Eze")

    assert PeopleStore(path).names() == {42: "Eze"}


def test_the_last_name_seen_wins(tmp_path):
    people = PeopleStore(tmp_path / "jobs.db")
    people.remember(42, "Eze")
    people.remember(42, "Ezequiel")
    people.remember(7, "Diego")

    assert people.names() == {42: "Ezequiel", 7: "Diego"}


def test_an_empty_name_is_not_stored(tmp_path):
    people = PeopleStore(tmp_path / "jobs.db")
    people.remember(42, "Eze")
    people.remember(42, "  ")

    assert people.names() == {42: "Eze"}


def test_a_chat_without_a_name_is_shown_by_its_number():
    assert display_name(42, {}) == "Chat 42"
    assert display_name(42, {42: "Eze"}) == "Eze"

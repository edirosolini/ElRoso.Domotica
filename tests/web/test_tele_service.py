"""El registro de la app de la tele y su consulta, sin HTTP."""

from datetime import datetime

import pytest

from homeauto.people import PeopleStore
from homeauto.screen import ScreenStore
from homeauto.tele import TeleLink, TeleStore
from homeauto.web.jobs import NotFound, WebError
from homeauto.web.tele import MAX_VERSION, TeleService

NOW = datetime(2026, 10, 21, 12, 0)
DEVICES = ("comedor", "recamara", "habitacion")


@pytest.fixture
def db(tmp_path):
    return tmp_path / "jobs.db"


@pytest.fixture
def screens(db):
    return ScreenStore(db)


@pytest.fixture
def store(db):
    return TeleStore(db)


@pytest.fixture
def service(db, screens, store):
    people = PeopleStore(db)
    people.remember(42, "Eze")
    return TeleService(
        link=TeleLink(store, clock=lambda: NOW),
        devices=DEVICES,
        people=people,
        chat_ids=[77, 42],
        screens=screens,
    )


def hello(**changes):
    body = {"alias": "comedor", "version_name": "1.0", "version_code": 3,
            "caps": ["play", "show"]}
    body.update(changes)
    return body


def test_setup_lists_the_screens_and_the_people(service):
    assert service.setup() == {
        "devices": ["comedor", "recamara", "habitacion"],
        "people": [{"chat_id": 42, "name": "Eze"}, {"chat_id": 77, "name": "Chat 77"}],
    }


def test_hello_registers_the_tele(service, store):
    answer = service.hello(hello(alias=" Comedor "), address="192.168.68.20")

    assert answer == {"alias": "comedor", "caps": ["play", "show"]}
    tele = store.get("comedor")
    assert (tele.version_name, tele.version_code, tele.caps, tele.address) == (
        "1.0", 3, ("play", "show"), "192.168.68.20"
    )
    assert tele.last_seen == NOW


def test_unknown_caps_are_ignored(service, store):
    answer = service.hello(hello(caps=["overlay", "volar", 7, "play", "play"]))

    assert answer["caps"] == ["overlay", "play"]
    assert store.get("comedor").caps == ("overlay", "play")


@pytest.mark.parametrize(
    "body",
    [
        hello(alias="cocina"),
        hello(alias=""),
        hello(alias=7),
        {"version_name": "1.0", "version_code": 3, "caps": []},
        hello(version_name="x" * (MAX_VERSION + 1)),
        hello(version_name=1.0),
        hello(version_code=-1),
        hello(version_code="3"),
        hello(version_code=True),
        hello(version_code=1.5),
        hello(caps="play"),
    ],
)
def test_a_bad_hello_is_a_400_and_registers_nothing(service, store, body):
    with pytest.raises(WebError) as caught:
        service.hello(body)

    assert caught.value.status == 400
    assert store.all() == []


def test_a_version_at_the_limit_is_accepted(service, store):
    service.hello(hello(version_name="x" * MAX_VERSION))

    assert store.get("comedor").version_name == "x" * MAX_VERSION


def test_poll_without_an_alarm_says_null(service):
    service.hello(hello())

    assert service.poll("comedor") == {"alarm": None, "orders": []}


def test_poll_brings_the_alarm_of_that_tele(service, screens):
    service.hello(hello())
    screens.show("comedor", 17)
    screens.show("recamara", 18)

    assert service.poll("Comedor") == {"alarm": 17, "orders": []}


def test_poll_counts_as_a_beat(service, store):
    service.hello(hello(), address="192.168.68.20")

    assert service.poll("comedor", address="192.168.68.21") == {"alarm": None, "orders": []}
    assert service.link.alive("comedor")


@pytest.mark.parametrize("alias", ["recamara", "cocina", ""])
def test_poll_of_an_unregistered_or_unknown_tele_is_a_404(service, alias):
    service.hello(hello())

    with pytest.raises(NotFound):
        service.poll(alias)


# --- las órdenes y su confirmación ---


def test_poll_brings_the_pending_orders(service):
    service.hello(hello())
    seq = service.link.send("comedor", "show", url="http://casa/alarma?job=7")

    assert service.poll("comedor")["orders"] == [
        {"seq": seq, "kind": "show", "url": "http://casa/alarma?job=7"}
    ]


@pytest.mark.parametrize("state", ["received", "done", "failed"])
def test_ack_records_what_the_app_says(service, state):
    service.hello(hello())
    seq = service.link.send("comedor", "play", url="u", min_volume=None, seconds=None)

    assert service.ack(" Comedor", {"seq": seq, "state": state}) == {"accepted": True}
    assert service.poll("comedor")["orders"] == []


def test_a_late_ack_is_answered_but_not_accepted(service):
    service.hello(hello())
    seq = service.link.send("comedor", "play", url="u", min_volume=None, seconds=None)
    service.link.cancel("comedor", seq)

    assert service.ack("comedor", {"seq": seq, "state": "done"}) == {"accepted": False}


@pytest.mark.parametrize(
    "body",
    [
        {"state": "done"},
        {"seq": "3", "state": "done"},
        {"seq": True, "state": "done"},
        {"seq": -1, "state": "done"},
        {"seq": 3},
        {"seq": 3, "state": "cancelled"},
        {"seq": 3, "state": 1},
    ],
)
def test_a_bad_ack_is_a_400(service, body):
    service.hello(hello())

    with pytest.raises(WebError) as error:
        service.ack("comedor", body)

    assert error.value.status == 400


@pytest.mark.parametrize("alias", ["recamara", "cocina", ""])
def test_ack_of_an_unregistered_or_unknown_tele_is_a_404(service, alias):
    service.hello(hello())

    with pytest.raises(NotFound):
        service.ack(alias, {"seq": 1, "state": "done"})

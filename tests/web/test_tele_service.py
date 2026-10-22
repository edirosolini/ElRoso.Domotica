"""El registro de la app de la tele y su consulta, sin HTTP."""

from datetime import datetime, timedelta

import pytest

from homeauto.people import Household, PeopleStore, PersonStore
from homeauto.quiet import AwayStore, Hush, HushStore, QuietHours
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.store import EVERYONE, PERSON
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
def awaiting(db):
    return AwaitingStore(db)


@pytest.fixture
def hush(db):
    return Hush(
        QuietHours.parse("22:00", "05:25"), HushStore(db), clock=lambda: NOW, away=AwayStore(db)
    )


@pytest.fixture
def service(db, screens, store, awaiting, hush):
    people = PeopleStore(db)
    people.remember(42, "Eze")
    return TeleService(
        link=TeleLink(store, clock=lambda: NOW),
        devices=DEVICES,
        people=people,
        chat_ids=[77, 42],
        screens=screens,
        awaiting=awaiting,
        quiet=hush,
        fallback="Comedor",
        clock=lambda: NOW,
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
        "persons": [],
    }


@pytest.fixture
def household(db):
    return Household(PersonStore(db), (42, 77))


def test_setup_with_an_empty_roster_falls_back_to_the_chats(service, household):
    service.household = household

    answer = service.setup()

    assert answer["persons"] == []
    assert answer["people"] == [{"chat_id": 42, "name": "Eze"}, {"chat_id": 77, "name": "Chat 77"}]


def test_setup_lists_the_roster_with_and_without_chat(service, household):
    household.add("Papá", 42)
    enano = household.add("Enano")
    service.household = household

    answer = service.setup()

    papa = household.by_chat(42)
    assert answer["persons"] == [
        {"id": enano.id, "name": "Enano", "chat_id": None},
        {"id": papa.id, "name": "Papá", "chat_id": 42},
    ]
    assert answer["people"] == [{"chat_id": 42, "name": "Papá"}]


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

    assert service.poll("comedor") == {"alarm": None, "reminders": [], "orders": []}


def test_poll_brings_the_alarm_of_that_tele(service, screens):
    service.hello(hello())
    screens.show("comedor", 17)
    screens.show("recamara", 18)

    assert service.poll("Comedor") == {"alarm": 17, "reminders": [], "orders": []}


def test_poll_counts_as_a_beat(service, store):
    service.hello(hello(), address="192.168.68.20")

    assert service.poll("comedor", address="192.168.68.21") == {"alarm": None, "reminders": [], "orders": []}
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


# --- los recordatorios que esperan «Hecho» ---


def ago(minutes):
    return NOW - timedelta(minutes=minutes)


def test_poll_brings_the_reminder_of_that_tele_and_not_of_another(service, awaiting):
    service.hello(hello())
    awaiting.remember(7, "tomar la pastilla", ago(5), devices="Comedor")
    awaiting.remember(8, "regar", ago(5), devices="recamara")

    assert service.poll("comedor")["reminders"] == [
        {"id": 7, "message": "tomar la pastilla", "for": None, "nags": 0}
    ]


def test_a_reminder_on_several_devices_reaches_each(service, awaiting):
    service.hello(hello())
    awaiting.remember(7, "tomar", ago(5), devices="habitacion, comedor")

    assert [item["id"] for item in service.poll("comedor")["reminders"]] == [7]


def test_a_reminder_without_devices_goes_to_the_default_device(service, awaiting):
    service.hello(hello())
    awaiting.remember(7, "tomar", ago(5))

    assert [item["id"] for item in service.poll("comedor")["reminders"]] == [7]


def test_a_reminder_without_devices_is_not_on_another_tele(service, awaiting):
    service.hello(hello(alias="recamara"))
    awaiting.remember(7, "tomar", ago(5))

    assert service.poll("recamara")["reminders"] == []


def test_a_reminder_past_the_snooze_window_is_not_shown(service, awaiting):
    service.hello(hello())
    awaiting.remember(7, "tomar", ago(31), devices="comedor")

    assert service.poll("comedor")["reminders"] == []


def test_in_quiet_hours_there_are_no_reminders(service, awaiting, db):
    service.hello(hello())
    awaiting.remember(7, "tomar", ago(5), devices="comedor")
    service.quiet = Hush(QuietHours.parse("11:00", "13:00"), HushStore(db), clock=lambda: NOW)

    assert service.poll("comedor")["reminders"] == []


def test_on_vacation_there_are_no_reminders(service, awaiting, hush):
    service.hello(hello())
    awaiting.remember(7, "tomar", ago(5), devices="comedor")
    hush.start_away(NOW + timedelta(days=3))

    assert service.poll("comedor")["reminders"] == []


def test_a_reminder_marked_done_is_gone(service, awaiting):
    service.hello(hello())
    awaiting.remember(7, "tomar", ago(5), devices="comedor")
    awaiting.take(7)

    assert service.poll("comedor")["reminders"] == []


def test_the_reminder_says_for_whom_and_its_nags(service, awaiting, household):
    papa = household.add("Papá", 42)
    service.household = household
    service.hello(hello())
    awaiting.remember(7, "tomar", ago(15), devices="comedor", assignee=PERSON,
                      assignee_id=papa.id)
    awaiting.mark_nagged(7, None)
    awaiting.remember(8, "regar", ago(10), devices="comedor", assignee=EVERYONE)
    awaiting.remember(9, "sacar la basura", ago(5), devices="comedor", assignee=PERSON,
                      assignee_id=999)

    assert service.poll("comedor")["reminders"] == [
        {"id": 7, "message": "tomar", "for": "Papá", "nags": 1},
        {"id": 8, "message": "regar", "for": "todos", "nags": 0},
        {"id": 9, "message": "sacar la basura", "for": None, "nags": 0},
    ]


def test_reminders_go_from_the_oldest_and_stop_at_five(service, awaiting):
    service.hello(hello())
    for job_id in range(1, 8):
        awaiting.remember(job_id, f"aviso {job_id}", ago(20 - job_id), devices="comedor")

    assert [item["id"] for item in service.poll("comedor")["reminders"]] == [1, 2, 3, 4, 5]

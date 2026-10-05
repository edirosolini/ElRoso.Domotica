"""Crear, editar y borrar avisos desde la pantalla, sin HTTP de por medio."""

from datetime import datetime, timedelta

import pytest

from homeauto.lists import ListStore
from homeauto.people import PeopleStore
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.history import HistoryStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import ALARM, DAILY, ONCE, REMINDER, WEEKLY, Store
from homeauto.web.jobs import (
    MAX_MESSAGE, JobsService, NotFound, ReadOnly, WebError, cancel_action,
)

EZE = 42
DIEGO = 7
NOW = datetime(2026, 10, 5, 12, 0)  # lunes


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)


@pytest.fixture
def parts(tmp_path):
    path = tmp_path / "jobs.db"
    store = Store(path)
    timer = FakeTimer()
    reminders = Reminders(
        store=store, timer=timer, announce=lambda job: None,
        awaiting=AwaitingStore(path), history=HistoryStore(path), clock=lambda: NOW,
    )
    people = PeopleStore(path)
    people.remember(EZE, "Eze")
    lists = ListStore(path)
    told = []
    spawned = []

    def notify(chat_id, text, actions=()):
        told.append((chat_id, text, actions))

    def spawn(work):
        spawned.append(work)
        work()

    def build(chat_ids=(EZE, DIEGO), notify=notify):
        return JobsService(
            reminders=reminders,
            store=store,
            devices=("comedor", "parlante"),
            chat_ids=chat_ids,
            people=people,
            lists=lists,
            notify=notify,
            clock=lambda: NOW,
            spawn=spawn,
        )

    return {"build": build, "store": store, "timer": timer, "told": told,
            "spawned": spawned, "lists": lists}


def payload(**changes):
    base = {
        "type": "alarm",
        "message": "arriba",
        "when": "2026-10-06T07:30",
        "repeat": ONCE,
        "days": [],
        "device": "",
        "author": EZE,
    }
    base.update(changes)
    return base


# --- la gente ---


def test_people_are_the_allowed_chats_with_their_names(parts):
    answer = parts["build"]().people()

    assert answer == {
        "writable": True,
        "people": [{"chat_id": DIEGO, "name": "Chat 7"}, {"chat_id": EZE, "name": "Eze"}],
        "devices": ["comedor", "parlante"],
    }


def test_without_allowed_chats_the_screen_is_read_only(parts):
    jobs = parts["build"](chat_ids=())

    assert jobs.people() == {"writable": False, "people": [], "devices": ["comedor", "parlante"]}
    with pytest.raises(ReadOnly):
        jobs.create(payload())


# --- crear ---


def test_create_schedules_it_for_the_chosen_author_and_arms_it(parts):
    created = parts["build"]().create(payload(author=DIEGO, device="comedor"))

    job = parts["store"].get(created["id"])
    assert (job.chat_id, job.when, job.message, job.kind, job.repeat, job.device) == (
        DIEGO, datetime(2026, 10, 6, 7, 30), "arriba", ALARM, ONCE, "comedor",
    )
    assert str(job.id) in parts["timer"].armed
    assert created["type"] == "alarm"
    assert created["author_name"] == "Chat 7"


@pytest.mark.parametrize(
    ("kind", "repeat", "days", "expected"),
    [
        ("timer", ONCE, [], (REMINDER, ONCE, [])),
        ("reminder", DAILY, [], (REMINDER, DAILY, [])),
        ("reminder", WEEKLY, [3, 5], (REMINDER, WEEKLY, [3, 5])),
        ("alarm", WEEKLY, [1], (ALARM, WEEKLY, [1])),
    ],
)
def test_each_type_lands_as_its_kind(parts, kind, repeat, days, expected):
    created = parts["build"]().create(payload(type=kind, repeat=repeat, days=days))

    job = parts["store"].get(created["id"])
    assert (job.kind, job.repeat, job.weekdays) == expected


def test_a_weekly_starts_on_its_first_day(parts):
    created = parts["build"]().create(payload(repeat=WEEKLY, days=[3], when="2026-10-05T07:30"))

    assert parts["store"].get(created["id"]).when == datetime(2026, 10, 7, 7, 30)


@pytest.mark.parametrize(
    "bad",
    [
        {"message": ""},
        {"message": "   "},
        {"message": "x" * (MAX_MESSAGE + 1)},
        {"message": 5},
        {"device": "cocina"},
        {"author": 1234},
        {"author": "42"},
        {"type": "despertador"},
        {"type": "reminder", "repeat": ONCE},
        {"type": "timer", "repeat": DAILY},
        {"repeat": WEEKLY, "days": []},
        {"repeat": WEEKLY, "days": [9]},
        {"repeat": WEEKLY, "days": "lun"},
        {"when": "2026-10-05T11:00"},
        {"when": "mañana"},
        {"when": None},
    ],
)
def test_a_bad_payload_is_refused_and_schedules_nothing(parts, bad):
    with pytest.raises(WebError) as caught:
        parts["build"]().create(payload(**bad))

    assert caught.value.status == 400
    assert parts["store"].pending() == []
    assert parts["told"] == []


def test_create_tells_every_chat_with_a_cancel_button(parts):
    created = parts["build"]().create(payload(message="sacar la basura"))

    assert [chat for chat, _, _ in parts["told"]] == [DIEGO, EZE]
    for _, text, actions in parts["told"]:
        assert "sacar la basura" in text
        assert "Eze" in text
        assert actions == ((f"Cancelar #{created['id']}", f"borrar {created['id']}"),)


def test_the_cancel_button_fits_in_telegram_with_a_big_id():
    """Telegram rechaza un callback_data de más de 64 bytes."""
    label, data = cancel_action(10 ** 18)

    assert data == f"borrar {10 ** 18}"
    assert len(data.encode()) <= 64
    assert len(label) <= 40


def test_the_notice_runs_apart_from_the_answer(parts):
    parts["build"]().create(payload())

    assert len(parts["spawned"]) == 1


def test_a_chat_that_fails_does_not_stop_the_others(parts):
    told = []

    def notify(chat_id, text, actions=()):
        if chat_id == DIEGO:
            raise RuntimeError("bloqueado")
        told.append(chat_id)

    parts["build"](notify=notify).create(payload())

    assert told == [EZE]


# --- leer, editar y borrar ---


def test_a_job_is_read_back_as_the_form_needs_it(parts):
    jobs = parts["build"]()
    created = jobs.create(payload(type="reminder", repeat=WEEKLY, days=[5, 1], device="comedor"))

    assert jobs.job(created["id"]) == {
        "id": created["id"],
        "type": "reminder",
        "message": "arriba",
        "when": "2026-10-09T07:30",
        "repeat": WEEKLY,
        "days": [1, 5],
        "device": "comedor",
        "author": EZE,
        "author_name": "Eze",
    }


def test_reading_a_missing_job_is_not_found(parts):
    with pytest.raises(NotFound):
        parts["build"]().job(99)


def test_update_edits_the_series_and_keeps_the_author(parts):
    jobs = parts["build"]()
    created = jobs.create(payload(author=DIEGO))
    parts["told"].clear()

    updated = jobs.update(
        created["id"],
        payload(type="reminder", message="la pastilla", repeat=DAILY, when="2026-10-05T21:00",
                author=EZE),
    )

    job = parts["store"].get(created["id"])
    assert (job.chat_id, job.kind, job.repeat, job.message, job.when) == (
        DIEGO, REMINDER, DAILY, "la pastilla", datetime(2026, 10, 5, 21, 0),
    )
    assert parts["timer"].armed[str(job.id)][0] == job.when
    assert updated["message"] == "la pastilla"
    assert [chat for chat, _, _ in parts["told"]] == [DIEGO, EZE]
    assert all("la pastilla" in text for _, text, _ in parts["told"])
    assert all(actions == ((f"Cancelar #{job.id}", f"borrar {job.id}"),)
               for _, _, actions in parts["told"])


def test_updating_a_missing_job_is_not_found(parts):
    with pytest.raises(NotFound):
        parts["build"]().update(99, payload())


def test_an_invalid_update_leaves_the_job_alone(parts):
    jobs = parts["build"]()
    created = jobs.create(payload())
    before = parts["store"].get(created["id"])

    with pytest.raises(WebError):
        jobs.update(created["id"], payload(message=""))

    assert parts["store"].get(created["id"]) == before


def test_delete_removes_anyones_job_and_tells_everyone(parts):
    jobs = parts["build"]()
    created = jobs.create(payload(author=DIEGO, message="arriba"))
    parts["told"].clear()

    jobs.delete(created["id"])

    assert parts["store"].get(created["id"]) is None
    assert str(created["id"]) not in parts["timer"].armed
    assert [chat for chat, _, _ in parts["told"]] == [DIEGO, EZE]
    assert all("arriba" in text and actions == () for _, text, actions in parts["told"])


def test_deleting_a_missing_job_is_not_found(parts):
    with pytest.raises(NotFound):
        parts["build"]().delete(99)


@pytest.mark.parametrize("write", ["update", "delete"])
def test_editing_is_also_read_only_without_allowed_chats(parts, write):
    created = parts["build"]().create(payload())
    jobs = parts["build"](chat_ids=())

    with pytest.raises(ReadOnly):
        if write == "update":
            jobs.update(created["id"], payload())
        else:
            jobs.delete(created["id"])


# --- las listas ---


def test_an_item_is_crossed_out_by_id(parts):
    parts["lists"].add("compras", ["leche", "pan"])
    [(milk, _), (bread, _)] = parts["lists"].entries("compras")

    assert parts["build"]().cross_out("compras", milk) == "leche"
    assert parts["lists"].entries("compras") == [(bread, "pan")]


@pytest.mark.parametrize(("name", "item"), [("compras", 99), ("ferreteria", 1)])
def test_crossing_out_what_is_not_there_is_not_found(parts, name, item):
    with pytest.raises(NotFound):
        parts["build"]().cross_out(name, item)


def test_crossing_out_is_read_only_without_allowed_chats(parts):
    parts["lists"].add("compras", ["leche"])
    [(milk, _)] = parts["lists"].entries("compras")

    with pytest.raises(ReadOnly):
        parts["build"](chat_ids=()).cross_out("compras", milk)
    assert parts["lists"].items("compras") == ["leche"]

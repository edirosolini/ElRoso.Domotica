"""A quién le llega un aviso asignado y con qué nombre lo llama la casa, también tras un reinicio."""

from datetime import datetime, timedelta

import pytest

from homeauto.holidays import MOVABLE, Holiday
from homeauto.people import Household, PersonStore
from homeauto.schedule.announcer import Announcer
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.history import HistoryStore
from homeauto.schedule.reminders import NAG_DELAY, NAG_LIMIT, RING_LIMIT, Reminders
from homeauto.schedule.ringing import RingingStore
from homeauto.schedule.store import (
    ALARM, EVERYONE, NOBODY, PERSON, REMINDER, WEEKLY, Store,
)

from tests.conftest import FakeSpeaker, StubRegistry

PAPA_CHAT = 42
CHINA_CHAT = 77
LOOSE_CHAT = 88
CHATS = (PAPA_CHAT, CHINA_CHAT, LOOSE_CHAT)
NOW = datetime(2026, 10, 12, 6, 59)
SOON = NOW + timedelta(minutes=1)


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def pop(self, key):
        return self.armed.pop(key)


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class Recorder:
    """Anota cada job que se anuncia, con su audiencia y su nombre."""

    def __init__(self):
        self.jobs = []

    def __call__(self, job, rings=0):
        self.jobs.append((job, rings))

    def stop(self, devices):
        pass


@pytest.fixture
def house(tmp_path):
    path = tmp_path / "jobs.db"
    household = Household(PersonStore(path), CHATS)
    people = {
        "papa": household.add("Papá", PAPA_CHAT),
        "china": household.add("China", CHINA_CHAT),
        "enano": household.add("Enano"),
    }
    timer = FakeTimer()
    clock = Clock(NOW)
    told = []
    announced = Recorder()

    def notify(chat_id, text, actions=()):
        told.append((chat_id, text))

    def build(holidays=None, resolve=household.get, find=household.by_name, announce=announced):
        return Reminders(
            store=Store(path),
            timer=timer,
            announce=announce,
            fired=FiredStore(path),
            awaiting=AwaitingStore(path),
            history=HistoryStore(path),
            ringing=RingingStore(path),
            stop_audio=announced.stop,
            notify=notify,
            clock=clock,
            chat_ids=CHATS,
            holidays=holidays,
            resolve=resolve,
            find=find,
        )

    return {
        "build": build, "people": people, "timer": timer, "clock": clock, "told": told,
        "announced": announced, "path": path, "household": household,
    }


def assign(house, who):
    """Los argumentos de asignación para «papa», «china», «enano», «todos» o «nadie»."""
    if who == "todos":
        return {"assignee": EVERYONE}
    if who == "nadie":
        return {"assignee": NOBODY}
    return {"assignee": PERSON, "assignee_id": house["people"][who].id}


def fire(house, reminders, who, kind=ALARM, message="sacar la basura", **kwargs):
    job = reminders.add(PAPA_CHAT, SOON, message, kind=kind, **assign(house, who), **kwargs)
    house["clock"].now = SOON
    house["timer"].pop(str(job.id))[1]()
    return job


def run(house, key):
    when, action = house["timer"].pop(key)
    house["clock"].now = when
    action()


def told_to(house, text):
    return sorted(chat for chat, said in house["told"] if text in said)


# --- la tabla -------------------------------------------------------------------


@pytest.mark.parametrize(
    "who, audience, addressee",
    [
        ("china", (CHINA_CHAT,), "China"),
        ("enano", None, "Enano"),
        ("todos", None, "Todos"),
        ("nadie", None, None),
    ],
)
def test_who_it_reaches_and_how_it_is_called(house, who, audience, addressee):
    fire(house, house["build"](), who)

    [(job, rings)] = house["announced"].jobs
    assert (job.audience, job.addressee, rings) == (audience, addressee, 0)


def test_only_the_chat_it_reached_can_snooze_it(house):
    fire(house, house["build"](), "china")

    fired = FiredStore(house["path"])
    assert fired.last(CHINA_CHAT) is not None
    assert fired.last(PAPA_CHAT) is None
    assert fired.last(LOOSE_CHAT) is None


def test_for_nobody_every_chat_can_snooze_it(house):
    fire(house, house["build"](), "nadie")

    fired = FiredStore(house["path"])
    assert all(fired.last(chat) is not None for chat in CHATS)


def test_the_history_keeps_who_it_was_for(house):
    fire(house, house["build"](), "china")

    [entry] = HistoryStore(house["path"]).between(NOW, NOW + timedelta(days=1))
    china = house["people"]["china"].id
    assert (entry.assignee, entry.assignee_id, entry.audience) == (PERSON, china, (CHINA_CHAT,))


def test_a_person_that_is_gone_counts_as_nobody(house):
    reminders = house["build"]()
    job = reminders.add(
        PAPA_CHAT, SOON, "regar", **assign(house, "china")
    )
    PersonStore(house["path"]).remove(house["people"]["china"].id)
    house["clock"].now = SOON
    house["timer"].pop(str(job.id))[1]()

    [(announced, _)] = house["announced"].jobs
    assert (announced.audience, announced.addressee) == (None, None)
    [entry] = HistoryStore(house["path"]).between(NOW, NOW + timedelta(days=1))
    assert (entry.assignee, entry.assignee_id) == (NOBODY, None)


def test_a_broken_padron_does_not_cost_the_alarm(house):
    def broken(_):
        raise RuntimeError("la base no contesta")

    fire(house, house["build"](resolve=broken, find=broken), "china")

    [(job, _)] = house["announced"].jobs
    assert (job.audience, job.addressee) == (None, None)


# --- turnos ---------------------------------------------------------------------


def turned(house, reminders, names, who="nadie"):
    job = reminders.add(
        PAPA_CHAT, SOON, "sacar la basura", repeat="daily", **assign(house, who)
    )
    reminders.set_rota(job.id, names, SOON.date())
    house["clock"].now = SOON
    house["timer"].pop(str(job.id))[1]()
    return job


def test_a_turn_of_someone_in_the_padron_goes_to_that_person(house):
    turned(house, house["build"](), ["China", "Papá"])

    [(job, _)] = house["announced"].jobs
    assert job.message == "Le toca a China: sacar la basura"
    assert job.audience == (CHINA_CHAT,)
    [entry] = HistoryStore(house["path"]).between(NOW, NOW + timedelta(days=1))
    assert (entry.assignee, entry.assignee_id) == (PERSON, house["people"]["china"].id)


def test_a_turn_of_someone_outside_the_padron_keeps_the_assignment(house):
    turned(house, house["build"](), ["Cin", "Die"], who="china")

    [(job, _)] = house["announced"].jobs
    assert job.message == "Le toca a Cin: sacar la basura"
    assert job.audience == (CHINA_CHAT,)


# --- re-aviso -------------------------------------------------------------------


def test_the_nags_go_to_its_audience_and_the_last_one_to_everyone(house):
    job = fire(house, house["build"](), "china", kind=REMINDER)
    key = f"nag:{job.id}"

    for _ in range(NAG_LIMIT - 1):
        run(house, key)
        assert told_to(house, "Sigue pendiente") == [CHINA_CHAT]
        house["told"].clear()
    run(house, key)

    assert told_to(house, "Sigue pendiente") == sorted(CHATS)


def test_a_nag_for_nobody_goes_to_everyone(house):
    job = fire(house, house["build"](), "nadie", kind=REMINDER)

    run(house, f"nag:{job.id}")

    assert told_to(house, "Sigue pendiente") == sorted(CHATS)


def test_after_a_restart_the_nag_reads_the_photo_not_the_job(house):
    job = fire(house, house["build"](), "china", kind=REMINDER)
    assert house["build"]().get(job.id) is None, "un timer se borra al sonar"
    house["timer"].armed.clear()

    house["clock"].now = SOON + NAG_DELAY
    house["build"]().start(house["clock"].now)

    assert told_to(house, "Sigue pendiente") == [CHINA_CHAT]


# --- «Hecho» y «Apagar» -----------------------------------------------------------


def test_done_by_the_assigned_person_tells_nobody_else(house):
    reminders = house["build"]()
    job = fire(house, reminders, "china", kind=REMINDER)

    reminders.done(CHINA_CHAT, job.id, "China")

    assert told_to(house, "marcó hecho") == []


@pytest.mark.parametrize("toucher", [PAPA_CHAT, None])
def test_done_by_someone_else_tells_the_assigned_person(house, toucher):
    reminders = house["build"]()
    job = fire(house, reminders, "china", kind=REMINDER)

    reminders.done(toucher, job.id, "Papá")

    assert told_to(house, "Papá marcó hecho") == [CHINA_CHAT]


def test_done_of_something_for_nobody_tells_the_others(house):
    reminders = house["build"]()
    job = fire(house, reminders, "nadie", kind=REMINDER)

    reminders.done(PAPA_CHAT, job.id, "Papá")

    assert told_to(house, "Papá marcó hecho") == [CHINA_CHAT, LOOSE_CHAT]


def test_turning_it_off_from_another_chat_tells_the_assigned_person(house):
    reminders = house["build"]()
    job = fire(house, reminders, "china")

    reminders.silence(PAPA_CHAT, job.id, "Papá")

    assert told_to(house, "Papá apagó") == [CHINA_CHAT]


# --- repetición de una alarma ---------------------------------------------------


def test_a_repetition_keeps_the_audience_and_the_name(house):
    job = fire(house, house["build"](), "china")

    run(house, f"ring:{job.id}")

    (_, _), (again, rings) = house["announced"].jobs
    assert (again.audience, again.addressee, rings) == ((CHINA_CHAT,), "China", 1)


def test_the_stop_at_the_limit_of_a_person_reaches_everyone(house):
    job = fire(house, house["build"](), "china")

    house["clock"].now = SOON + RING_LIMIT
    house["build"]()._ring(job.id)

    assert told_to(house, "Dejé de sonar") == sorted(CHATS)


def test_after_a_restart_the_repetition_reads_the_photo(house):
    job = fire(house, house["build"](), "china")
    house["timer"].armed.clear()
    house["announced"].jobs.clear()

    house["clock"].now = SOON + timedelta(minutes=6)
    house["build"]().start(house["clock"].now)

    [(again, rings)] = house["announced"].jobs
    assert (again.id, again.audience, again.addressee, rings) == (
        job.id, (CHINA_CHAT,), "China", 1,
    )


# --- posponer -------------------------------------------------------------------


def test_snoozing_copies_the_assignment(house):
    reminders = house["build"]()
    fire(house, reminders, "china", kind=REMINDER)

    again = reminders.snooze(CHINA_CHAT, timedelta(minutes=10))

    assert (again.assignee, again.assignee_id) == (PERSON, house["people"]["china"].id)
    assert again.kind == REMINDER


def test_a_chat_it_did_not_reach_cannot_snooze_it(house):
    reminders = house["build"]()
    fire(house, reminders, "china")

    assert reminders.snooze(PAPA_CHAT, timedelta(minutes=10)) is None


def test_snoozing_forgets_it_for_the_whole_audience(house):
    reminders = house["build"]()
    fire(house, reminders, "todos")

    reminders.snooze(PAPA_CHAT, timedelta(minutes=10))

    assert reminders.snooze(CHINA_CHAT, timedelta(minutes=10)) is None


# --- feriado --------------------------------------------------------------------


def test_a_skipped_holiday_is_told_to_its_audience(house):
    holiday = Holiday(SOON.date(), MOVABLE, "Feriado")
    reminders = house["build"](holidays=lambda day: holiday if day == holiday.day else None)

    fire(
        house, reminders, "china", repeat=WEEKLY, days=(SOON.isoweekday(),), skip_holidays=True
    )

    assert told_to(house, "Feriado") == [CHINA_CHAT]
    assert house["announced"].jobs == []


# --- el chat recibe solo chats ----------------------------------------------------


@pytest.mark.parametrize("who", ["papa", "china", "enano", "todos", "nadie"])
def test_notify_never_gets_an_id_that_is_not_a_chat(house, who):
    sent = []

    def notify(chat_id, text, actions=()):
        sent.append(chat_id)

    speaker = FakeSpeaker("parlante")
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=notify,
        fallback="parlante",
        chat_ids=CHATS,
    )
    reminders = house["build"](announce=announcer)
    reminders.notify = notify
    job = fire(house, reminders, who, kind=REMINDER)
    for _ in range(NAG_LIMIT):
        run(house, f"nag:{job.id}")
    reminders.done(None, job.id, "Alguien")

    assert sent
    assert set(sent) <= set(CHATS)

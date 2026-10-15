"""El nombre del turno llega al aviso, a lo que sonó, al «Hecho», al historial y al pulidor."""

from datetime import date, datetime, timedelta

import pytest

from homeauto.schedule.announcer import Announcer
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.history import HistoryStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.ringing import RingingStore
from homeauto.schedule.store import ALARM, REMINDER, WEEKLY, Job, Store

from tests.conftest import FakeSpeaker, StubRegistry

OWNER = 42
OTHER = 99
# Lunes 12 de octubre de 2026, a las ocho de la noche.
NOW = datetime(2026, 10, 12, 19, 55)
SOON = datetime(2026, 10, 12, 20, 0)
MONDAY = date(2026, 10, 12)
DAY = (NOW - timedelta(days=1), NOW + timedelta(days=2))


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def fire(self, key):
        self.armed[key][1]()


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def house(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    clock = Clock(NOW)
    announced = []
    reminders = Reminders(
        store=Store(path),
        timer=timer,
        announce=lambda job, **_: announced.append(job),
        fired=FiredStore(path),
        awaiting=AwaitingStore(path),
        notify=lambda *args: None,
        clock=clock,
        chat_ids=(OWNER, OTHER),
        history=HistoryStore(path),
        ringing=RingingStore(path),
    )
    return reminders, timer, clock, announced


def rota(reminders, kind=REMINDER):
    """Un job semanal de los lunes que rota entre Cin y Die desde esta semana."""
    job = reminders.add(OWNER, SOON, "sacar la basura", repeat=WEEKLY, days=[1], kind=kind)
    reminders.store.set_rota(job.id, ["Cin", "Die"], MONDAY)
    return job


def ring(reminders, timer, clock, job, at=SOON):
    clock.now = at
    timer.fire(str(job.id))


def test_the_announcement_says_whose_turn_it_is(house):
    reminders, timer, clock, announced = house
    job = rota(reminders)

    ring(reminders, timer, clock, job)

    assert [said.message for said in announced] == ["Le toca a Cin: sacar la basura"]


def test_the_next_week_it_is_the_other_one(house):
    reminders, timer, clock, announced = house
    job = rota(reminders)
    ring(reminders, timer, clock, job)

    ring(reminders, timer, clock, job, at=SOON + timedelta(days=7))

    assert announced[-1].message == "Le toca a Die: sacar la basura"


def test_the_stored_job_keeps_the_plain_message(house):
    reminders, timer, clock, _ = house
    job = rota(reminders)

    ring(reminders, timer, clock, job)

    assert reminders.get(job.id).message == "sacar la basura"


def test_what_fired_carries_the_name_for_every_chat(house):
    reminders, timer, clock, _ = house
    job = rota(reminders)

    ring(reminders, timer, clock, job)

    for chat in (OWNER, OTHER):
        assert reminders.fired.last(chat).message == "Le toca a Cin: sacar la basura"


def test_what_waits_for_done_carries_the_name(house):
    reminders, timer, clock, _ = house
    job = rota(reminders)
    ring(reminders, timer, clock, job)

    assert reminders.awaiting.get(job.id).message == "Le toca a Cin: sacar la basura"
    assert reminders.done(OTHER, job.id, "Die") == "Le toca a Cin: sacar la basura"


def test_the_history_carries_the_name(house):
    reminders, timer, clock, _ = house
    job = rota(reminders)

    ring(reminders, timer, clock, job)

    assert [entry.message for entry in reminders.history.between(*DAY)] == [
        "Le toca a Cin: sacar la basura"
    ]


def test_a_ringing_alarm_carries_the_name(house):
    reminders, timer, clock, _ = house
    job = rota(reminders, kind=ALARM)

    ring(reminders, timer, clock, job)

    assert reminders.ringing.get(job.id).message == "Le toca a Cin: sacar la basura"


def test_snoozing_keeps_the_name(house):
    reminders, timer, clock, _ = house
    job = rota(reminders)
    ring(reminders, timer, clock, job)

    snoozed = reminders.snooze(OTHER, timedelta(minutes=10))

    assert snoozed.message == "Le toca a Cin: sacar la basura"


def test_a_job_without_rota_says_its_message_as_is(house):
    reminders, timer, clock, announced = house
    job = reminders.add(OWNER, SOON, "sacar la basura", repeat=WEEKLY, days=[1], kind=REMINDER)

    ring(reminders, timer, clock, job)

    assert announced[0].message == "sacar la basura"


class KeepingPolisher:
    """Reescribe como lo haría el pulidor y anota qué tenía que conservar."""

    def __init__(self):
        self.kept = []

    def __call__(self, text, must_keep=()):
        self.kept.append(tuple(must_keep))
        return text.replace("Le toca a", "Hoy le toca a")


def test_the_name_must_survive_the_polisher():
    polish = KeepingPolisher()
    speaker = FakeSpeaker("parlante")
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda *args: None,
        fallback="parlante",
        polish=polish,
    )
    job = Job(id=7, chat_id=OWNER, when=SOON, message="Le toca a Cin: sacar la basura",
              repeat=WEEKLY, days="1", kind=REMINDER, rota="Cin,Die", rota_from=MONDAY)

    announcer(job)

    assert polish.kept == [("Cin",)]
    assert speaker.said == ["Hoy le toca a Cin: sacar la basura"]


def test_without_a_turn_nothing_extra_must_survive():
    polish = KeepingPolisher()
    announcer = Announcer(
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        notify=lambda *args: None,
        fallback="parlante",
        polish=polish,
    )

    announcer(Job(id=7, chat_id=OWNER, when=SOON, message="arriba"))

    assert polish.kept == [()]

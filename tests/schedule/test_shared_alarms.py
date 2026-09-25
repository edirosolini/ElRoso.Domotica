"""Una alarma le llega a toda la casa, y cualquiera la puede posponer una vez."""

from datetime import datetime, timedelta

import pytest

from homeauto.schedule.announcer import Announcer
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import Job, Store

from tests.conftest import FakeSpeaker, StubRegistry
from tests.schedule.test_reminders import FakeTimer

OWNER = 42
OTHER = 77
SOON = datetime(2026, 9, 25, 7, 30)
JOB = Job(id=7, chat_id=OWNER, when=SOON, message="arriba")


def build_announcer(chat_ids):
    speaker = FakeSpeaker("parlante")
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda chat_id, text, actions=(): sent.append((chat_id, text, actions)),
        fallback="parlante",
        actions=(("Posponer 10 min", "posponer 10m"),),
        chat_ids=chat_ids,
    )
    return announcer, speaker, sent


def test_an_alarm_is_written_to_every_chat():
    announcer, _, sent = build_announcer([OWNER, OTHER])

    announcer(JOB)

    assert sorted(chat for chat, _, _ in sent) == [OWNER, OTHER]


def test_every_chat_gets_the_snooze_buttons():
    announcer, _, sent = build_announcer([OWNER, OTHER])

    announcer(JOB)

    assert all(actions for _, _, actions in sent)


def test_the_speaker_says_it_once():
    announcer, speaker, _ = build_announcer([OWNER, OTHER])

    announcer(JOB)

    assert speaker.said == ["arriba"]


def test_without_a_chat_list_it_only_reaches_whoever_set_it():
    announcer, _, sent = build_announcer([])

    announcer(JOB)

    assert [chat for chat, _, _ in sent] == [OWNER]


def test_a_broken_chat_does_not_cost_the_other_one():
    sent = []

    def notify(chat_id, text, actions=()):
        if chat_id == OWNER:
            raise RuntimeError("telegram no contesta")
        sent.append(chat_id)

    Announcer(
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        notify=notify,
        fallback="parlante",
        chat_ids=[OWNER, OTHER],
    )(JOB)

    assert sent == [OTHER]


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def shared(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    reminders = Reminders(
        store=Store(path),
        timer=timer,
        announce=lambda job: None,
        fired=FiredStore(path),
        clock=Clock(SOON),
        chat_ids=[OWNER, OTHER],
    )
    return reminders, timer


def test_anyone_can_snooze_an_alarm_someone_else_set(shared):
    reminders, timer = shared
    job = reminders.add(OWNER, SOON, "arriba", device="comedor")
    timer.fire(str(job.id))

    snoozed = reminders.snooze(OTHER, timedelta(minutes=10))

    assert snoozed.message == "arriba"
    assert snoozed.device == "comedor"
    assert snoozed.chat_id == OTHER


def test_once_snoozed_the_other_chat_has_nothing_to_snooze(shared):
    reminders, timer = shared
    job = reminders.add(OWNER, SOON, "arriba")
    timer.fire(str(job.id))

    reminders.snooze(OTHER, timedelta(minutes=10))

    assert reminders.snooze(OWNER, timedelta(minutes=30)) is None

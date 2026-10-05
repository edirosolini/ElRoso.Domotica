"""Lo que `Reminders` deja en el historial al sonar, re-avisar, marcar, posponer y cancelar."""

from datetime import datetime, timedelta

import pytest

from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.history import HistoryStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import ALARM, REMINDER, Store

OWNER = 42
OTHER = 99
NOW = datetime(2026, 10, 5, 8, 0)
SOON = NOW + timedelta(minutes=5)
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
def parts(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    clock = Clock(NOW)
    history = HistoryStore(path)
    seen_at_announce = []

    def announce(job):
        seen_at_announce.append(history.between(*DAY))

    def build(announce=announce, history=history):
        return Reminders(
            store=Store(path),
            timer=timer,
            announce=announce,
            fired=FiredStore(path),
            awaiting=AwaitingStore(path),
            notify=lambda *args: None,
            clock=clock,
            chat_ids=(OWNER, OTHER),
            history=history,
        )

    return build, timer, clock, history, seen_at_announce


def ring(reminders, timer, clock, **kwargs):
    job = reminders.add(OWNER, SOON, kwargs.pop("message", "la pastilla"), **kwargs)
    clock.now = SOON
    timer.fire(str(job.id))
    return job


def test_firing_records_the_row_before_announcing(parts):
    build, timer, clock, history, seen = parts

    job = ring(build(), timer, clock, kind=REMINDER, repeat="daily")

    [[before]] = seen
    assert before.job_id == job.id
    assert not before.announced
    [entry] = history.between(*DAY)
    assert entry.chat_id == OWNER
    assert entry.kind == REMINDER
    assert entry.repeat == "daily"
    assert entry.message == "la pastilla"
    assert entry.fired_at == SOON
    assert entry.announced


def test_an_announce_that_broke_is_kept_as_not_said(parts):
    build, timer, clock, history, _ = parts

    def broken(job):
        raise RuntimeError("parlante apagado")

    ring(build(announce=broken), timer, clock, kind=REMINDER)

    [entry] = history.between(*DAY)
    assert not entry.announced


def test_alarms_are_recorded_with_their_kind(parts):
    build, timer, clock, history, _ = parts

    ring(build(), timer, clock, message="arriba")

    [entry] = history.between(*DAY)
    assert (entry.kind, entry.message, entry.closed) == (ALARM, "arriba", None)


def test_each_nag_is_counted(parts):
    build, timer, clock, history, _ = parts
    job = ring(build(), timer, clock, kind=REMINDER)

    for _ in range(2):
        when, action = timer.armed.pop(f"nag:{job.id}")
        clock.now = when
        action()

    assert history.between(*DAY)[0].nags == 2


def test_done_closes_the_row_with_who(parts):
    build, timer, clock, history, _ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)
    clock.now = SOON + timedelta(minutes=2)

    reminders.done(OTHER, job.id, "Ana")

    [entry] = history.between(*DAY)
    assert (entry.closed, entry.done_by, entry.done_at) == ("done", "Ana", clock.now)
    assert entry.closed_at == clock.now


def test_done_twice_keeps_the_first(parts):
    build, timer, clock, history, _ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)
    reminders.done(OTHER, job.id, "Ana")

    reminders.done(OWNER, job.id, "Eze")

    assert history.between(*DAY)[0].done_by == "Ana"


def test_snooze_closes_the_original_and_the_snoozed_opens_its_own(parts):
    build, timer, clock, history, _ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)
    clock.now = SOON + timedelta(minutes=1)

    later = reminders.snooze(OWNER, timedelta(minutes=10))

    [original] = history.between(*DAY)
    assert (original.job_id, original.closed, original.snoozed_at) == (job.id, "snooze", clock.now)
    assert original.closed_at == clock.now

    clock.now = later.when
    timer.fire(str(later.id))

    first, second = history.between(*DAY)
    assert first.closed == "snooze"
    assert (second.job_id, second.kind, second.closed) == (later.id, REMINDER, None)


def test_cancelling_a_job_that_rang_closes_its_row(parts):
    build, timer, clock, history, _ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER, repeat="daily")
    clock.now = SOON + timedelta(minutes=3)

    assert reminders.cancel(OWNER, job.id)

    [entry] = history.between(*DAY)
    assert (entry.closed, entry.closed_at) == ("cancel", clock.now)


def test_cancelling_a_daily_alarm_leaves_yesterday_untouched(parts):
    build, timer, clock, history, _ = parts
    reminders = build()
    job = ring(reminders, timer, clock, message="arriba", repeat="daily")
    clock.now = SOON + timedelta(hours=20)

    assert reminders.cancel(OWNER, job.id)

    [yesterday] = history.between(*DAY)
    assert (yesterday.closed, yesterday.closed_at) == (None, None)


def test_cancelling_a_reminder_already_done_leaves_its_row_as_done(parts):
    build, timer, clock, history, _ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER, repeat="daily")
    reminders.done(OWNER, job.id, "Eze")

    assert reminders.cancel(OWNER, job.id)

    assert history.between(*DAY)[0].closed == "done"


class BrokenHistory:
    """Un historial que revienta en cada escritura."""

    def __getattr__(self, name):
        def broken(*args, **kwargs):
            raise RuntimeError("disco lleno")

        return broken


def test_a_broken_history_does_not_stop_the_reminder(parts, tmp_path):
    build, timer, clock, _, _ = parts
    said = []
    reminders = build(announce=said.append, history=BrokenHistory())

    job = ring(reminders, timer, clock, kind=REMINDER, repeat="daily")

    assert [j.id for j in said] == [job.id]
    assert reminders.fired.last(OWNER).job_id == job.id
    assert reminders.awaiting.get(job.id).message == "la pastilla"
    assert f"nag:{job.id}" in timer.armed
    assert str(job.id) in timer.armed

    when, action = timer.armed[f"nag:{job.id}"]
    clock.now = when
    action()
    assert reminders.awaiting.get(job.id).nags == 1
    assert reminders.done(OWNER, job.id, "Eze") == "la pastilla"
    clock.now = SOON + timedelta(days=1)
    timer.fire(str(job.id))
    assert reminders.snooze(OWNER, timedelta(minutes=10)) is not None
    assert reminders.cancel(OWNER, job.id)


def test_cancelling_something_that_never_rang_writes_nothing(parts):
    build, timer, clock, history, _ = parts
    reminders = build()
    job = reminders.add(OWNER, SOON, "la pastilla", kind=REMINDER)

    assert reminders.cancel(OWNER, job.id)

    assert history.between(*DAY) == []


def test_without_history_everything_works_as_before(parts):
    build, timer, clock, history, _ = parts
    reminders = build(history=None)
    job = ring(reminders, timer, clock, kind=REMINDER, repeat="daily")
    when, action = timer.armed[f"nag:{job.id}"]
    clock.now = when
    action()

    assert reminders.done(OWNER, job.id, "Eze") == "la pastilla"
    clock.now = SOON + timedelta(days=1)
    timer.fire(str(job.id))
    assert reminders.snooze(OWNER, timedelta(minutes=10)) is not None
    assert reminders.cancel(OWNER, job.id)
    assert history.between(*DAY) == []

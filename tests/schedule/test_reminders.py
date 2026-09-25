from datetime import datetime, timedelta

import pytest

from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import Store

OWNER = 42
STRANGER = 99
NOW = datetime(2026, 8, 29, 21, 0)
SOON = NOW + timedelta(minutes=10)


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def fire(self, key):
        self.armed[key][1]()


@pytest.fixture
def parts(tmp_path):
    store = Store(tmp_path / "jobs.db")
    timer = FakeTimer()
    announced = []
    reminders = Reminders(store=store, timer=timer, announce=announced.append)
    return reminders, store, timer, announced


def test_adding_persists_and_arms_the_timer(parts):
    reminders, store, timer, _ = parts

    job = reminders.add(OWNER, SOON, "sacá la pizza")

    assert store.get(job.id) == job
    assert timer.armed[str(job.id)][0] == SOON


def test_firing_announces_and_forgets_a_one_shot(parts):
    reminders, store, timer, announced = parts
    job = reminders.add(OWNER, SOON, "sacá la pizza")

    timer.fire(str(job.id))

    assert [j.message for j in announced] == ["sacá la pizza"]
    assert store.get(job.id) is None
    assert str(job.id) not in timer.armed


def test_daily_job_is_announced_and_rearmed_for_tomorrow(parts):
    reminders, store, timer, announced = parts
    job = reminders.add(OWNER, SOON, "arriba", repeat="daily")

    timer.fire(str(job.id))

    assert len(announced) == 1
    assert store.get(job.id).when == SOON + timedelta(days=1)
    assert timer.armed[str(job.id)][0] == SOON + timedelta(days=1)


def test_daily_job_keeps_firing(parts):
    reminders, _, timer, announced = parts
    job = reminders.add(OWNER, SOON, "arriba", repeat="daily")

    timer.fire(str(job.id))
    timer.fire(str(job.id))

    assert len(announced) == 2


def test_cancel_removes_and_disarms(parts):
    reminders, store, timer, _ = parts
    job = reminders.add(OWNER, SOON, "sacá la pizza")

    assert reminders.cancel(OWNER, job.id) is True
    assert store.get(job.id) is None
    assert str(job.id) not in timer.armed


def test_cannot_cancel_someone_elses_job(parts):
    reminders, store, _, _ = parts
    job = reminders.add(OWNER, SOON, "mia")

    assert reminders.cancel(STRANGER, job.id) is False
    assert store.get(job.id) is not None


def test_cancel_of_unknown_id_is_false(parts):
    reminders, _, _, _ = parts

    assert reminders.cancel(OWNER, 12345) is False


def test_list_only_shows_your_own(parts):
    reminders, _, _, _ = parts
    reminders.add(OWNER, SOON, "mia")
    reminders.add(STRANGER, SOON, "ajena")

    assert [j.message for j in reminders.list(OWNER)] == ["mia"]


def test_start_arms_everything_still_pending(tmp_path):
    path = tmp_path / "jobs.db"
    seeded = Store(path)
    job = seeded.add(OWNER, SOON, "sobrevive")

    timer = FakeTimer()
    announced = []
    Reminders(store=Store(path), timer=timer, announce=announced.append).start(now=NOW)

    assert timer.armed[str(job.id)][0] == SOON
    assert announced == []


def test_start_fires_what_was_missed_while_it_was_down(tmp_path):
    path = tmp_path / "jobs.db"
    missed = NOW - timedelta(minutes=5)
    Store(path).add(OWNER, missed, "esto se perdió")

    announced = []
    Reminders(store=Store(path), timer=FakeTimer(), announce=announced.append).start(now=NOW)

    assert [j.message for j in announced] == ["esto se perdió"]


# --- semanales -------------------------------------------------------------


def test_weekly_job_jumps_to_the_next_day_it_asked_for(parts):
    reminders, store, timer, announced = parts
    friday = datetime(2026, 9, 4, 5, 30)

    job = reminders.add(OWNER, friday, "arriba", repeat="weekly", days=(1, 2, 3, 4, 5))
    timer.fire(str(job.id))

    assert announced[0].message == "arriba"
    assert store.get(job.id).when == datetime(2026, 9, 7, 5, 30)  # el lunes, no el sábado
    assert timer.armed[str(job.id)][0] == datetime(2026, 9, 7, 5, 30)


def test_weekly_job_survives_the_firing(parts):
    reminders, store, timer, _ = parts
    monday = datetime(2026, 8, 31, 5, 30)

    job = reminders.add(OWNER, monday, "arriba", repeat="weekly", days=(1,))
    timer.fire(str(job.id))

    assert store.get(job.id) is not None
    assert store.get(job.id).when == datetime(2026, 9, 7, 5, 30)


# --- posponer --------------------------------------------------------------

from homeauto.schedule.fired import FiredStore
from homeauto.schedule.reminders import SNOOZE_WINDOW


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def snoozing(tmp_path):
    path = tmp_path / "jobs.db"
    store = Store(path)
    fired = FiredStore(path)
    timer = FakeTimer()
    announced = []
    clock = Clock(SOON)
    reminders = Reminders(
        store=store, timer=timer, announce=announced.append, fired=fired, clock=clock
    )
    return reminders, store, timer, fired, clock


def test_what_fires_is_remembered_before_it_is_announced(tmp_path):
    """El botón llega con el aviso: tiene que poder usarse apenas aparece."""
    path = tmp_path / "jobs.db"
    fired = FiredStore(path)
    seen = []
    timer = FakeTimer()
    reminders = Reminders(
        store=Store(path),
        timer=timer,
        announce=lambda job: seen.append(fired.last(job.chat_id)),
        fired=fired,
        clock=Clock(SOON),
    )
    job = reminders.add(OWNER, SOON, "arriba", device="comedor")

    timer.fire(str(job.id))

    assert seen[0].message == "arriba"
    assert seen[0].device == "comedor"
    assert seen[0].at == SOON


def test_snoozing_schedules_the_same_thing_later(snoozing):
    reminders, store, timer, _, clock = snoozing
    job = reminders.add(OWNER, SOON, "arriba", device="comedor")
    timer.fire(str(job.id))
    clock.now = SOON + timedelta(minutes=1)

    snoozed = reminders.snooze(OWNER, timedelta(minutes=10))

    assert snoozed.message == "arriba"
    assert snoozed.device == "comedor"
    assert snoozed.repeat == "once"
    assert snoozed.when == clock.now + timedelta(minutes=10)
    assert timer.armed[str(snoozed.id)][0] == snoozed.when


def test_snoozing_a_daily_alarm_leaves_the_daily_alone(snoozing):
    reminders, store, timer, _, _ = snoozing
    daily = reminders.add(OWNER, SOON, "arriba", repeat="daily")
    timer.fire(str(daily.id))

    reminders.snooze(OWNER, timedelta(minutes=10))

    assert store.get(daily.id).when == SOON + timedelta(days=1)
    assert len(reminders.list(OWNER)) == 2


def test_nothing_to_snooze_when_nothing_fired(snoozing):
    reminders, _, _, _, _ = snoozing

    assert reminders.snooze(OWNER, timedelta(minutes=10)) is None
    assert reminders.list(OWNER) == []


def test_an_old_alarm_cannot_be_snoozed(snoozing):
    reminders, _, timer, _, clock = snoozing
    job = reminders.add(OWNER, SOON, "arriba")
    timer.fire(str(job.id))
    clock.now = SOON + SNOOZE_WINDOW + timedelta(seconds=1)

    assert reminders.snooze(OWNER, timedelta(minutes=10)) is None
    assert reminders.list(OWNER) == []


def test_the_edge_of_the_window_still_counts(snoozing):
    reminders, _, timer, _, clock = snoozing
    job = reminders.add(OWNER, SOON, "arriba")
    timer.fire(str(job.id))
    clock.now = SOON + SNOOZE_WINDOW

    assert reminders.snooze(OWNER, timedelta(minutes=10)) is not None


def test_a_second_tap_does_not_schedule_it_twice(snoozing):
    reminders, _, timer, _, _ = snoozing
    job = reminders.add(OWNER, SOON, "arriba")
    timer.fire(str(job.id))

    reminders.snooze(OWNER, timedelta(minutes=10))

    assert reminders.snooze(OWNER, timedelta(minutes=10)) is None
    assert len(reminders.list(OWNER)) == 1


def test_a_snoozed_alarm_can_be_snoozed_again(snoozing):
    reminders, _, timer, _, clock = snoozing
    job = reminders.add(OWNER, SOON, "arriba")
    timer.fire(str(job.id))
    snoozed = reminders.snooze(OWNER, timedelta(minutes=10))
    clock.now = snoozed.when
    timer.fire(str(snoozed.id))

    again = reminders.snooze(OWNER, timedelta(minutes=5))

    assert again.message == "arriba"


def test_someone_elses_alarm_is_not_yours_to_snooze(snoozing):
    reminders, _, timer, _, _ = snoozing
    job = reminders.add(STRANGER, SOON, "ajena")
    timer.fire(str(job.id))

    assert reminders.snooze(OWNER, timedelta(minutes=10)) is None


def test_without_memory_there_is_nothing_to_snooze(parts):
    reminders, _, timer, _ = parts
    job = reminders.add(OWNER, SOON, "arriba")
    timer.fire(str(job.id))

    assert reminders.snooze(OWNER, timedelta(minutes=10)) is None

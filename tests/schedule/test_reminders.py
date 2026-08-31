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

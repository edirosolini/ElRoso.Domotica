from datetime import datetime

import pytest

from homeauto.schedule.store import Job, Store

OWNER = 42
OTHER = 99
T1 = datetime(2026, 8, 30, 7, 30)
T2 = datetime(2026, 8, 30, 9, 0)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "jobs.db")


def test_added_job_comes_back_with_an_id(store):
    job = store.add(OWNER, T1, "arriba")

    assert isinstance(job, Job)
    assert job.id > 0
    assert job.chat_id == OWNER
    assert job.when == T1
    assert job.message == "arriba"
    assert job.repeat == "once"


def test_ids_do_not_repeat(store):
    first = store.add(OWNER, T1, "una")
    second = store.add(OWNER, T2, "otra")

    assert first.id != second.id


def test_pending_is_sorted_by_time(store):
    store.add(OWNER, T2, "segunda")
    store.add(OWNER, T1, "primera")

    assert [j.message for j in store.pending()] == ["primera", "segunda"]


def test_pending_can_be_filtered_by_chat(store):
    store.add(OWNER, T1, "mia")
    store.add(OTHER, T2, "ajena")

    assert [j.message for j in store.pending(chat_id=OWNER)] == ["mia"]


def test_get_returns_the_job(store):
    job = store.add(OWNER, T1, "arriba")

    assert store.get(job.id) == job


def test_get_of_an_unknown_id_is_none(store):
    assert store.get(12345) is None


def test_remove_deletes_it(store):
    job = store.add(OWNER, T1, "arriba")

    assert store.remove(job.id) is True
    assert store.get(job.id) is None
    assert store.pending() == []


def test_remove_of_an_unknown_id_reports_false(store):
    assert store.remove(999) is False


def test_reschedule_moves_the_time(store):
    job = store.add(OWNER, T1, "arriba", repeat="daily")

    store.reschedule(job.id, T2)

    assert store.get(job.id).when == T2


def test_jobs_survive_a_restart(tmp_path):
    path = tmp_path / "jobs.db"
    job = Store(path).add(OWNER, T1, "sobrevive")

    reopened = Store(path)

    assert reopened.get(job.id) == job


def test_daily_repeat_is_kept(store):
    job = store.add(OWNER, T1, "todos los dias", repeat="daily")

    assert store.get(job.id).repeat == "daily"


def test_unknown_repeat_is_rejected(store):
    with pytest.raises(ValueError, match="repeat"):
        store.add(OWNER, T1, "mal", repeat="cada dos horas")


# --- semanales -------------------------------------------------------------


def test_weekly_job_remembers_its_days(store):
    job = store.add(OWNER, T1, "arriba", repeat="weekly", days=(1, 2, 3, 4, 5))

    assert job.weekdays == [1, 2, 3, 4, 5]
    assert store.get(job.id).weekdays == [1, 2, 3, 4, 5]


def test_weekly_without_days_is_rejected(store):
    with pytest.raises(ValueError, match="días"):
        store.add(OWNER, T1, "arriba", repeat="weekly")


def test_a_job_without_days_reports_none(store):
    assert store.add(OWNER, T1, "arriba").weekdays == []


def test_days_column_is_added_to_an_older_database(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,"
            " fires_at TEXT NOT NULL, message TEXT NOT NULL, repeat TEXT NOT NULL DEFAULT 'once')"
        )

    store = Store(path)
    job = store.add(OWNER, T1, "arriba", repeat="weekly", days=(6, 7))

    assert store.get(job.id).weekdays == [6, 7]


# --- mensuales -------------------------------------------------------------


def test_monthly_job_remembers_its_day(store):
    job = store.add(OWNER, T1, "pagar la luz", repeat="monthly", monthday=10)

    assert job.monthday == 10
    assert job.is_monthly
    assert store.get(job.id).monthday == 10


def test_monthly_without_a_day_is_rejected(store):
    with pytest.raises(ValueError, match="día"):
        store.add(OWNER, T1, "pagar la luz", repeat="monthly")


def test_a_job_that_is_not_monthly_has_no_day(store):
    assert store.add(OWNER, T1, "arriba").monthday is None


def test_monthday_column_is_added_to_an_older_database(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,"
            " fires_at TEXT NOT NULL, message TEXT NOT NULL, repeat TEXT NOT NULL DEFAULT 'once',"
            " device TEXT, days TEXT, kind TEXT NOT NULL DEFAULT 'alarm')"
        )

    store = Store(path)
    job = store.add(OWNER, T1, "pagar la luz", repeat="monthly", monthday=31)

    assert store.get(job.id).monthday == 31


def test_update_can_turn_a_job_monthly(store):
    job = store.add(OWNER, T1, "arriba")

    updated = store.update(job.id, T2, "pagar la luz", repeat="monthly", monthday=30)

    assert (updated.repeat, updated.monthday) == ("monthly", 30)


# --- feriados --------------------------------------------------------------

WORKDAYS = (1, 2, 3, 4, 5)


def test_a_weekly_job_can_skip_holidays(store):
    job = store.add(OWNER, T1, "el colegio", repeat="weekly", days=WORKDAYS, skip_holidays=True)

    assert job.skip_holidays is True
    assert store.get(job.id).skip_holidays is True


def test_by_default_a_job_rings_on_holidays(store):
    job = store.add(OWNER, T1, "el colegio", repeat="weekly", days=WORKDAYS)

    assert store.get(job.id).skip_holidays is False


@pytest.mark.parametrize(
    ("repeat", "extra"),
    [("once", {}), ("daily", {}), ("monthly", {"monthday": 10})],
)
def test_only_a_weekly_job_can_skip_holidays(store, repeat, extra):
    with pytest.raises(ValueError):
        store.add(OWNER, T1, "arriba", repeat=repeat, skip_holidays=True, **extra)
    assert store.pending() == []


def test_update_can_turn_skipping_holidays_on_and_off(store):
    job = store.add(OWNER, T1, "el colegio", repeat="weekly", days=WORKDAYS)

    on = store.update(job.id, T2, "el colegio", repeat="weekly", days=WORKDAYS, skip_holidays=True)
    off = store.update(job.id, T2, "el colegio", repeat="weekly", days=WORKDAYS)

    assert on.skip_holidays is True
    assert off.skip_holidays is False


def test_update_refuses_skipping_holidays_on_a_daily(store):
    job = store.add(OWNER, T1, "arriba", repeat="daily")

    with pytest.raises(ValueError):
        store.update(job.id, T2, "arriba", repeat="daily", skip_holidays=True)
    assert store.get(job.id).when == T1


def test_skip_holidays_column_is_added_to_an_older_database(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,"
            " fires_at TEXT NOT NULL, message TEXT NOT NULL, repeat TEXT NOT NULL DEFAULT 'once',"
            " device TEXT, days TEXT, kind TEXT NOT NULL DEFAULT 'alarm', monthday INTEGER)"
        )
        conn.execute(
            "INSERT INTO jobs (chat_id, fires_at, message, repeat, days)"
            " VALUES (42, '2026-10-05T07:00:00', 'viejo', 'weekly', '1,2,3,4,5')"
        )

    store = Store(path)

    [old] = store.pending()
    assert old.skip_holidays is False
    job = store.add(OWNER, T1, "nuevo", repeat="weekly", days=WORKDAYS, skip_holidays=True)
    assert store.get(job.id).skip_holidays is True


# --- editar ----------------------------------------------------------------


def test_update_rewrites_the_job_and_keeps_its_id_and_owner(store):
    job = store.add(OWNER, T1, "arriba")

    updated = store.update(
        job.id, T2, "a desayunar", repeat="weekly", device="comedor", days=[5, 1], kind="reminder"
    )

    assert updated == Job(
        id=job.id, chat_id=OWNER, when=T2, message="a desayunar", repeat="weekly",
        device="comedor", days="1,5", kind="reminder",
    )
    assert store.get(job.id) == updated


def test_update_of_a_missing_job_returns_none(store):
    assert store.update(7, T1, "arriba") is None


@pytest.mark.parametrize(
    "bad",
    [{"repeat": "monthly"}, {"kind": "despertador"}, {"repeat": "weekly", "days": []}],
)
def test_update_validates_like_add(store, bad):
    job = store.add(OWNER, T1, "arriba")

    with pytest.raises(ValueError):
        store.update(job.id, T2, "otra", **bad)

    assert store.get(job.id) == job

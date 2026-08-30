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

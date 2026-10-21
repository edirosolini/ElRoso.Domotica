"""Las alarmas que están sonando y nadie apagó todavía."""

import sqlite3
import threading
from datetime import datetime, timedelta

import pytest

from homeauto.schedule.ringing import RingingStore

NOW = datetime(2026, 10, 15, 7, 0)


@pytest.fixture
def store(tmp_path):
    return RingingStore(tmp_path / "jobs.db")


def test_a_ringing_alarm_is_kept_with_what_it_needs_to_ring_again(store):
    store.remember(7, 42, "arriba", "parlante,cocina", NOW)

    ringing = store.get(7)
    assert ringing.job_id == 7
    assert ringing.chat_id == 42
    assert ringing.message == "arriba"
    assert ringing.devices == "parlante,cocina"
    assert ringing.fired_at == NOW
    assert ringing.rings == 0
    assert ringing.next_ring is None


def test_ringing_again_counts_and_sets_the_next(store):
    store.remember(7, 42, "arriba", None, NOW)

    store.mark_rang(7)
    store.set_next(7, NOW + timedelta(minutes=2))

    ringing = store.get(7)
    assert ringing.rings == 1
    assert ringing.next_ring == NOW + timedelta(minutes=2)


def test_setting_the_next_of_one_that_was_turned_off_says_so(store):
    assert store.set_next(7, NOW) is False


def test_ringing_again_from_the_start_resets_the_count(store):
    store.remember(7, 42, "arriba", None, NOW)
    store.mark_rang(7)
    store.set_next(7, NOW + timedelta(minutes=1))

    store.remember(7, 42, "arriba", None, NOW + timedelta(days=1))

    ringing = store.get(7)
    assert ringing.rings == 0
    assert ringing.next_ring is None
    assert ringing.fired_at == NOW + timedelta(days=1)


def test_take_turns_it_off_once(store):
    store.remember(7, 42, "arriba", None, NOW)

    assert store.take(7).message == "arriba"
    assert store.take(7) is None
    assert store.get(7) is None


def test_two_takes_at_once_turn_it_off_once(tmp_path):
    path = tmp_path / "jobs.db"
    RingingStore(path).remember(7, 42, "arriba", None, NOW)
    results = []
    gate = threading.Barrier(8)

    def take():
        store = RingingStore(path)
        gate.wait()
        results.append(store.take(7))

    threads = [threading.Thread(target=take) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len([found for found in results if found is not None]) == 1


def test_all_lists_what_is_ringing(store):
    store.remember(7, 42, "arriba", None, NOW)
    store.remember(8, 42, "colegio", None, NOW)

    assert sorted(ringing.job_id for ringing in store.all()) == [7, 8]


def test_an_old_table_gets_the_new_columns(tmp_path):
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE ringing (job_id INTEGER PRIMARY KEY, chat_id INTEGER,"
            " message TEXT NOT NULL, fired_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO ringing (job_id, chat_id, message, fired_at) VALUES (7, 42, 'arriba', ?)",
            (NOW.isoformat(),),
        )

    ringing = RingingStore(path).get(7)

    assert ringing.devices is None
    assert ringing.rings == 0
    assert ringing.next_ring is None


def test_it_keeps_the_assignment_and_who_it_reached(store):
    store.remember(7, 42, "arriba", None, NOW, assignee="person", assignee_id=3, audience=(77,))

    ringing = store.get(7)
    assert (ringing.assignee, ringing.assignee_id, ringing.audience) == ("person", 3, (77,))


def test_an_old_row_reached_everyone(tmp_path):
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE ringing (job_id INTEGER PRIMARY KEY, chat_id INTEGER,"
            " message TEXT NOT NULL, fired_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO ringing (job_id, chat_id, message, fired_at) VALUES (7, 42, 'arriba', ?)",
            (NOW.isoformat(),),
        )

    ringing = RingingStore(path).get(7)

    assert (ringing.assignee, ringing.assignee_id, ringing.audience) == ("none", None, None)

"""Lo que espera su «Hecho», leído entero para la pantalla de control."""

from datetime import datetime

from homeauto.schedule.awaiting import AwaitingStore

AT = datetime(2026, 10, 19, 8, 0)


def test_all_lists_what_waits_in_the_order_it_rang(tmp_path):
    store = AwaitingStore(tmp_path / "jobs.db")
    store.remember(9, "colegio", AT.replace(minute=30))
    store.remember(7, "pastilla", AT)

    waiting = store.all()

    assert [(wait.job_id, wait.message) for wait in waiting] == [(7, "pastilla"), (9, "colegio")]


def test_all_does_not_take_anything_out(tmp_path):
    store = AwaitingStore(tmp_path / "jobs.db")
    store.remember(7, "pastilla", AT)

    store.all()

    assert store.get(7) is not None


def test_all_is_empty_when_nothing_waits(tmp_path):
    assert AwaitingStore(tmp_path / "jobs.db").all() == []


def test_drop_before_only_takes_out_what_rang_before_the_cutoff(tmp_path):
    store = AwaitingStore(tmp_path / "jobs.db")
    store.remember(7, "pastilla", AT)

    assert store.drop_before(7, AT) is False
    assert store.get(7) is not None
    assert store.drop_before(7, AT.replace(minute=1)) is True
    assert store.get(7) is None
    assert store.drop_before(7, AT.replace(minute=1)) is False


def test_it_keeps_the_assignment_and_who_it_reached(tmp_path):
    store = AwaitingStore(tmp_path / "jobs.db")

    store.remember(7, "pastilla", AT, assignee="person", assignee_id=3, audience=(42, 77))

    wait = store.get(7)
    assert (wait.assignee, wait.assignee_id, wait.audience) == ("person", 3, (42, 77))


def test_an_old_row_reached_everyone(tmp_path):
    import sqlite3

    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE awaiting_done (job_id INTEGER PRIMARY KEY, message TEXT NOT NULL,"
            " fired_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO awaiting_done (job_id, message, fired_at) VALUES (7, 'pastilla', ?)",
            (AT.isoformat(),),
        )

    wait = AwaitingStore(path).get(7)

    assert (wait.assignee, wait.assignee_id, wait.audience) == ("none", None, None)

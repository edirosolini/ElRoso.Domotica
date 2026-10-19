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

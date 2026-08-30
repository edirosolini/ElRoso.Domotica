from datetime import datetime, timedelta

from homeauto.agenda.seen import SeenStore

NOW = datetime(2026, 8, 30, 9, 0)


def test_nothing_is_seen_at_first(tmp_path):
    assert SeenStore(tmp_path / "jobs.db").was_seen("a") is False


def test_marking_makes_it_seen(tmp_path):
    store = SeenStore(tmp_path / "jobs.db")

    store.mark("a", NOW)

    assert store.was_seen("a") is True
    assert store.was_seen("b") is False


def test_marking_twice_is_harmless(tmp_path):
    store = SeenStore(tmp_path / "jobs.db")

    store.mark("a", NOW)
    store.mark("a", NOW)

    assert store.was_seen("a") is True


def test_it_survives_a_restart(tmp_path):
    path = tmp_path / "jobs.db"
    SeenStore(path).mark("a", NOW)

    assert SeenStore(path).was_seen("a") is True, "tras reiniciar no puede volver a avisar lo mismo"


def test_old_entries_are_forgotten(tmp_path):
    store = SeenStore(tmp_path / "jobs.db")
    store.mark("viejo", NOW - timedelta(days=3))
    store.mark("nuevo", NOW)

    store.forget_before(NOW - timedelta(days=1))

    assert store.was_seen("viejo") is False
    assert store.was_seen("nuevo") is True


def test_it_shares_the_file_with_the_jobs(tmp_path):
    from homeauto.schedule.store import Store

    path = tmp_path / "jobs.db"
    jobs = Store(path)
    seen = SeenStore(path)

    seen.mark("a", NOW)
    job = jobs.add(1, NOW, "hola")

    assert seen.was_seen("a") and jobs.get(job.id) is not None

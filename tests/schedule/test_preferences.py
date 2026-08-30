from homeauto.schedule.preferences import Preferences

OWNER = 42
OTHER = 99


def test_no_preference_at_first(tmp_path):
    prefs = Preferences(tmp_path / "jobs.db")

    assert prefs.default_device(OWNER) is None


def test_remembers_the_chosen_device(tmp_path):
    prefs = Preferences(tmp_path / "jobs.db")

    prefs.set_default_device(OWNER, "tv")

    assert prefs.default_device(OWNER) == "tv"


def test_each_chat_chooses_its_own(tmp_path):
    prefs = Preferences(tmp_path / "jobs.db")

    prefs.set_default_device(OWNER, "tv")
    prefs.set_default_device(OTHER, "parlante")

    assert prefs.default_device(OWNER) == "tv"
    assert prefs.default_device(OTHER) == "parlante"


def test_choosing_again_replaces(tmp_path):
    prefs = Preferences(tmp_path / "jobs.db")

    prefs.set_default_device(OWNER, "tv")
    prefs.set_default_device(OWNER, "parlante")

    assert prefs.default_device(OWNER) == "parlante"


def test_the_choice_survives_a_restart(tmp_path):
    path = tmp_path / "jobs.db"
    Preferences(path).set_default_device(OWNER, "tv")

    assert Preferences(path).default_device(OWNER) == "tv"


def test_it_shares_the_file_with_the_jobs(tmp_path):
    from datetime import datetime
    from homeauto.schedule.store import Store

    path = tmp_path / "jobs.db"
    store = Store(path)
    prefs = Preferences(path)

    prefs.set_default_device(OWNER, "tv")
    job = store.add(OWNER, datetime(2026, 8, 30, 7, 30), "arriba")

    assert prefs.default_device(OWNER) == "tv"
    assert store.get(job.id) is not None

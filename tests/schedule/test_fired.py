from datetime import datetime

from homeauto.schedule.fired import FiredStore

OWNER = 42
OTHER = 99
AT = datetime(2026, 9, 25, 7, 30)


def test_nothing_fired_yet(tmp_path):
    assert FiredStore(tmp_path / "jobs.db").last(OWNER) is None


def test_remembers_the_last_one_that_fired(tmp_path):
    fired = FiredStore(tmp_path / "jobs.db")

    fired.remember(OWNER, "arriba", "parlante,comedor", AT)

    last = fired.last(OWNER)
    assert last.message == "arriba"
    assert last.device == "parlante,comedor"
    assert last.at == AT


def test_a_newer_one_replaces_the_older(tmp_path):
    fired = FiredStore(tmp_path / "jobs.db")
    fired.remember(OWNER, "arriba", None, AT)

    fired.remember(OWNER, "sacá la pizza", "parlante", AT.replace(minute=45))

    assert fired.last(OWNER).message == "sacá la pizza"


def test_each_chat_keeps_its_own(tmp_path):
    fired = FiredStore(tmp_path / "jobs.db")
    fired.remember(OWNER, "mía", None, AT)
    fired.remember(OTHER, "ajena", None, AT)

    assert fired.last(OWNER).message == "mía"


def test_forgetting_leaves_nothing(tmp_path):
    fired = FiredStore(tmp_path / "jobs.db")
    fired.remember(OWNER, "arriba", None, AT)

    fired.forget(OWNER)

    assert fired.last(OWNER) is None


def test_survives_a_restart(tmp_path):
    FiredStore(tmp_path / "jobs.db").remember(OWNER, "arriba", None, AT)

    assert FiredStore(tmp_path / "jobs.db").last(OWNER).message == "arriba"

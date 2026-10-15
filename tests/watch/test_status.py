"""El estado de cada chequeo, con la confirmación de una caída y sus re-avisos."""

import sqlite3
from datetime import datetime, timedelta

from homeauto.watch.status import Status, StatusStore

NOW = datetime(2026, 10, 15, 3, 0)
LATER = NOW + timedelta(minutes=5)


def down(store, name="vps", alerted=True):
    store.save(Status(name, False, 2, alerted, "timeout", NOW))


def test_a_new_row_starts_without_confirmation_nor_reminders(tmp_path):
    store = StatusStore(tmp_path / "jobs.db")
    down(store)

    state = store.get("vps")

    assert state.acked_by == ""
    assert state.acked_at is None
    assert state.reminders == 0
    assert state.next_reminder is None


def test_an_alerted_outage_can_be_acknowledged_once(tmp_path):
    store = StatusStore(tmp_path / "jobs.db")
    down(store)

    assert store.acknowledge("vps", "Eze", LATER) is True
    assert store.acknowledge("vps", "Ana", LATER) is False

    state = store.get("vps")
    assert state.acked_by == "Eze"
    assert state.acked_at == LATER


def test_a_service_that_is_up_cannot_be_acknowledged(tmp_path):
    store = StatusStore(tmp_path / "jobs.db")
    store.save(Status("vps", True, 0, False, "ok", NOW))

    assert store.acknowledge("vps", "Eze", LATER) is False
    assert store.get("vps").acked_by == ""


def test_an_outage_nobody_was_told_about_cannot_be_acknowledged(tmp_path):
    store = StatusStore(tmp_path / "jobs.db")
    down(store, alerted=False)

    assert store.acknowledge("vps", "Eze", LATER) is False


def test_an_unknown_service_cannot_be_acknowledged(tmp_path):
    store = StatusStore(tmp_path / "jobs.db")

    assert store.acknowledge("nada", "Eze", LATER) is False


def test_saving_the_round_keeps_the_acknowledgement_and_the_reminders(tmp_path):
    """Una confirmación que entra en medio de una vuelta no se puede perder."""
    store = StatusStore(tmp_path / "jobs.db")
    down(store)
    store.plan_reminder("vps", 2, LATER)
    store.acknowledge("vps", "Eze", NOW)

    store.save(Status("vps", False, 3, True, "otra vez timeout", LATER))

    state = store.get("vps")
    assert (state.acked_by, state.reminders, state.next_reminder) == ("Eze", 2, LATER)
    assert state.failures == 3


def test_planning_a_reminder_keeps_the_acknowledgement(tmp_path):
    store = StatusStore(tmp_path / "jobs.db")
    down(store)
    store.acknowledge("vps", "Eze", NOW)

    store.plan_reminder("vps", 1, LATER)

    assert store.get("vps").acked_by == "Eze"


def test_clearing_the_alert_forgets_confirmation_and_reminders(tmp_path):
    store = StatusStore(tmp_path / "jobs.db")
    down(store)
    store.plan_reminder("vps", 3, LATER)
    store.acknowledge("vps", "Eze", NOW)

    store.clear_alert("vps")

    state = store.get("vps")
    assert (state.acked_by, state.acked_at, state.reminders, state.next_reminder) == (
        "", None, 0, None,
    )


def test_a_deployed_table_gets_the_new_columns_without_reminding(tmp_path):
    """Lo que ya estaba avisado al desplegar queda sin próximo re-aviso."""
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE service_status (name TEXT PRIMARY KEY, up INTEGER NOT NULL, "
            "failures INTEGER NOT NULL DEFAULT 0, alerted INTEGER NOT NULL DEFAULT 0, "
            "detail TEXT NOT NULL DEFAULT '', since TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO service_status VALUES ('vps', 0, 5, 1, 'timeout', ?)", (NOW.isoformat(),)
        )

    store = StatusStore(path)

    state = store.get("vps")
    assert state.alerted is True
    assert state.next_reminder is None
    assert state.acked_by == ""
    assert store.acknowledge("vps", "Eze", LATER) is True

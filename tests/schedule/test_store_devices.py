import sqlite3
from datetime import datetime

from homeauto.schedule.store import Store

OWNER = 42
T1 = datetime(2026, 8, 30, 7, 30)

OLD_SCHEMA = """
CREATE TABLE jobs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id  INTEGER NOT NULL,
    fires_at TEXT    NOT NULL,
    message  TEXT    NOT NULL,
    repeat   TEXT    NOT NULL DEFAULT 'once'
);
"""


def test_job_remembers_its_device(tmp_path):
    store = Store(tmp_path / "jobs.db")

    job = store.add(OWNER, T1, "arriba", device="tv")

    assert store.get(job.id).device == "tv"


def test_a_job_without_a_device_uses_whatever_is_default_later(tmp_path):
    store = Store(tmp_path / "jobs.db")

    job = store.add(OWNER, T1, "arriba")

    assert store.get(job.id).device is None


def test_an_old_database_gets_the_new_column(tmp_path):
    """El CT ya tiene una base creada sin la columna: no puede romperse al desplegar."""
    path = tmp_path / "jobs.db"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO jobs (chat_id, fires_at, message, repeat) VALUES (?,?,?,?)",
        (OWNER, T1.isoformat(), "de la version vieja", "once"),
    )
    conn.commit()
    conn.close()

    store = Store(path)

    survivors = store.pending()
    assert [j.message for j in survivors] == ["de la version vieja"]
    assert survivors[0].device is None


def test_migrating_twice_is_harmless(tmp_path):
    path = tmp_path / "jobs.db"
    Store(path).add(OWNER, T1, "arriba", device="tv")

    reopened = Store(path)

    assert reopened.pending()[0].device == "tv"

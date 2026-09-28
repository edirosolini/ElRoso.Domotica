"""Alarma y recordatorio: se agendan igual y suenan distinto."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from homeauto.schedule.announcer import Announcer
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import ALARM, REMINDER, Job, Store
from homeauto.voice import chime

from tests.conftest import FakeSpeaker, StubRegistry

OWNER = 42
OTHER = 99
NOW = datetime(2026, 9, 28, 7, 55)
SOON = NOW + timedelta(minutes=5)

SNOOZE = (("Posponer 10 min", "posponer 10m"),)
DONE = (("✅ Hecho", "hecho {job}"),) + SNOOZE


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def fire(self, key):
        self.armed[key][1]()


# --- persistencia ------------------------------------------------------------


def test_a_job_is_an_alarm_unless_told_otherwise(tmp_path):
    store = Store(tmp_path / "jobs.db")

    job = store.add(OWNER, SOON, "arriba")

    assert store.get(job.id).kind == ALARM
    assert not store.get(job.id).is_reminder


def test_a_reminder_is_stored_as_such(tmp_path):
    store = Store(tmp_path / "jobs.db")

    job = store.add(OWNER, SOON, "la pastilla", repeat="daily", kind=REMINDER)

    assert store.get(job.id).kind == REMINDER
    assert store.get(job.id).is_reminder


def test_an_unknown_kind_is_refused(tmp_path):
    with pytest.raises(ValueError):
        Store(tmp_path / "jobs.db").add(OWNER, SOON, "x", kind="sirena")


def test_an_old_database_keeps_its_jobs_as_alarms(tmp_path):
    """La base del CT no tiene la columna: lo que ya estaba sigue siendo alarma."""
    path = tmp_path / "jobs.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,"
        " fires_at TEXT NOT NULL, message TEXT NOT NULL, repeat TEXT NOT NULL DEFAULT 'once',"
        " device TEXT, days TEXT);"
    )
    conn.execute(
        "INSERT INTO jobs (chat_id, fires_at, message) VALUES (?, ?, ?)",
        (OWNER, SOON.isoformat(), "arriba"),
    )
    conn.commit()
    conn.close()

    [job] = Store(path).pending()

    assert job.kind == ALARM


# --- cómo suena --------------------------------------------------------------


def announce(job, **kwargs):
    speaker = FakeSpeaker("parlante")
    sent = []
    Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda chat_id, text, actions=(): sent.append((chat_id, text, actions)),
        fallback="parlante",
        actions=SNOOZE,
        reminder_actions=DONE,
        **kwargs,
    )(job)
    return speaker, sent


ALARM_JOB = Job(id=7, chat_id=OWNER, when=SOON, message="arriba", repeat="daily")
REMINDER_JOB = Job(
    id=8, chat_id=OWNER, when=SOON, message="la pastilla", repeat="daily", kind=REMINDER
)


def test_an_alarm_rings_the_alarm_beeps():
    speaker, _ = announce(ALARM_JOB)

    assert speaker.chimes == [chime.ALARM]


def test_a_reminder_rings_the_soft_beep():
    speaker, _ = announce(REMINDER_JOB)

    assert speaker.said == ["la pastilla"]
    assert speaker.chimes == [chime.SOFT]


def test_the_chat_tells_an_alarm_from_a_reminder():
    _, [(_, alarm, _)] = announce(ALARM_JOB)
    _, [(_, reminder, _)] = announce(REMINDER_JOB)

    assert alarm.startswith("⏰")
    assert "alarma de todos los días" in alarm
    assert reminder.startswith("🔔")
    assert "recordatorio de todos los días" in reminder
    assert "alarma" not in reminder


def test_a_weekly_reminder_names_its_days():
    job = Job(id=9, chat_id=OWNER, when=SOON, message="al colegio", repeat="weekly",
              days="1,2,3,4,5", kind=REMINDER)

    _, [(_, text, _)] = announce(job)

    assert "(recordatorio de lun, mar, mié, jue, vie)" in text


def test_only_a_reminder_offers_done_and_it_names_its_job():
    _, [(_, _, alarm)] = announce(ALARM_JOB)
    _, [(_, _, reminder)] = announce(REMINDER_JOB)

    assert alarm == SNOOZE
    assert reminder[0] == ("✅ Hecho", "hecho 8")
    assert reminder[1:] == SNOOZE


# --- hecho -------------------------------------------------------------------


@pytest.fixture
def parts(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    told = []
    reminders = Reminders(
        store=Store(path),
        timer=timer,
        announce=lambda job: None,
        fired=FiredStore(path),
        awaiting=AwaitingStore(path),
        notify=lambda chat_id, text: told.append((chat_id, text)),
        clock=lambda: NOW,
        chat_ids=[OWNER, OTHER],
    )
    return reminders, timer, told


def test_done_tells_the_others_who_did_it(parts):
    reminders, timer, told = parts
    job = reminders.add(OWNER, SOON, "la pastilla", repeat="daily", kind=REMINDER)
    timer.fire(str(job.id))

    message = reminders.done(OWNER, job.id, "Eze")

    assert message == "la pastilla"
    assert told == [(OTHER, "✅ Eze marcó hecho: «la pastilla»")]


def test_done_twice_only_counts_once(parts):
    reminders, timer, told = parts
    job = reminders.add(OWNER, SOON, "la pastilla", repeat="daily", kind=REMINDER)
    timer.fire(str(job.id))
    reminders.done(OWNER, job.id, "Eze")

    assert reminders.done(OTHER, job.id, "Ana") is None
    assert len(told) == 1


def test_done_works_after_something_else_rang(parts):
    """La pastilla y el colegio suenan juntos: marcar uno no depende del orden."""
    reminders, timer, _ = parts
    pill = reminders.add(OWNER, SOON, "la pastilla", repeat="daily", kind=REMINDER)
    school = reminders.add(OWNER, SOON + timedelta(minutes=1), "al colegio",
                           repeat="daily", kind=REMINDER)
    timer.fire(str(pill.id))
    timer.fire(str(school.id))

    assert reminders.done(OWNER, pill.id, "Eze") == "la pastilla"


def test_a_one_shot_timer_can_be_done_after_it_is_gone(parts):
    reminders, timer, _ = parts
    job = reminders.add(OWNER, SOON, "sacá la pizza", kind=REMINDER)
    timer.fire(str(job.id))

    assert reminders.done(OWNER, job.id, "Eze") == "sacá la pizza"


def test_an_alarm_is_never_waiting_to_be_done(parts):
    reminders, timer, _ = parts
    job = reminders.add(OWNER, SOON, "arriba", repeat="daily")
    timer.fire(str(job.id))

    assert reminders.done(OWNER, job.id, "Eze") is None


def test_done_leaves_nothing_to_postpone(parts):
    reminders, timer, _ = parts
    job = reminders.add(OWNER, SOON, "la pastilla", repeat="daily", kind=REMINDER)
    timer.fire(str(job.id))

    reminders.done(OWNER, job.id, "Eze")

    assert reminders.snooze(OWNER, timedelta(minutes=10)) is None
    assert reminders.snooze(OTHER, timedelta(minutes=10)) is None


def test_a_postponed_reminder_is_still_a_reminder(parts):
    reminders, timer, _ = parts
    job = reminders.add(OWNER, SOON, "la pastilla", repeat="daily", kind=REMINDER)
    timer.fire(str(job.id))

    later = reminders.snooze(OWNER, timedelta(minutes=10))

    assert later.kind == REMINDER


def test_a_postponed_alarm_is_still_an_alarm(parts):
    reminders, timer, _ = parts
    job = reminders.add(OWNER, SOON, "arriba")
    timer.fire(str(job.id))

    assert reminders.snooze(OWNER, timedelta(minutes=10)).kind == ALARM


# --- la tabla de lo que espera un «hecho» -------------------------------------


def test_a_stale_wait_is_pruned(tmp_path):
    awaiting = AwaitingStore(tmp_path / "jobs.db")
    awaiting.remember(1, "vieja", NOW - timedelta(days=2))

    awaiting.remember(2, "nueva", NOW)

    assert awaiting.take(1) is None
    assert awaiting.take(2) == "nueva"


def test_ringing_again_replaces_the_wait(tmp_path):
    awaiting = AwaitingStore(tmp_path / "jobs.db")
    awaiting.remember(1, "la pastilla", NOW - timedelta(hours=1))

    awaiting.remember(1, "la pastilla", NOW)

    assert awaiting.take(1) == "la pastilla"
    assert awaiting.take(1) is None

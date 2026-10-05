"""Un recordatorio que sonó y nadie marcó vuelve a avisar por el chat."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.reminders import NAG_DELAY, NAG_LIMIT, SNOOZE_WINDOW, Reminders
from homeauto.schedule.store import REMINDER, Store

OWNER = 42
OTHER = 99
NOW = datetime(2026, 10, 5, 8, 0)
SOON = NOW + timedelta(minutes=5)

DONE = (("✅ Hecho", "hecho {job}"),)


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def fire(self, key):
        self.armed[key][1]()


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def nag_key(job):
    return f"nag:{job.id}"


@pytest.fixture
def parts(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    clock = Clock(NOW)
    told = []
    announced = []

    def notify(chat_id, text, actions=()):
        told.append((chat_id, text, actions))

    def build(chat_ids=(OWNER, OTHER), notify=notify):
        return Reminders(
            store=Store(path),
            timer=timer,
            announce=announced.append,
            fired=FiredStore(path),
            awaiting=AwaitingStore(path),
            notify=notify,
            clock=clock,
            chat_ids=chat_ids,
            nag_actions=DONE,
        )

    return build, timer, clock, told, announced, path


def ring(reminders, timer, clock, **kwargs):
    job = reminders.add(OWNER, SOON, kwargs.pop("message", "la pastilla"), **kwargs)
    clock.now = SOON
    timer.fire(str(job.id))
    return job


def nag(timer, clock, job):
    when, action = timer.armed.pop(nag_key(job))
    clock.now = when
    action()


# --- cuándo -----------------------------------------------------------------


def test_a_reminder_that_rang_arms_its_nag(parts):
    build, timer, clock, *_ = parts
    job = ring(build(), timer, clock, kind=REMINDER)

    assert timer.armed[nag_key(job)][0] == SOON + NAG_DELAY


def test_an_alarm_never_nags(parts):
    build, timer, clock, *_ = parts
    job = ring(build(), timer, clock)

    assert nag_key(job) not in timer.armed


def test_the_nag_keeps_its_own_key_when_a_daily_rearms(parts):
    build, timer, clock, *_ = parts
    job = ring(build(), timer, clock, kind=REMINDER, repeat="daily")

    assert str(job.id) in timer.armed
    assert nag_key(job) in timer.armed


def test_it_nags_every_five_minutes_and_stops_after_the_limit(parts):
    build, timer, clock, told, *_ = parts
    job = ring(build(), timer, clock, kind=REMINDER)

    moments = []
    while nag_key(job) in timer.armed:
        nag(timer, clock, job)
        moments.append(clock.now)

    assert NAG_LIMIT == 3
    assert moments == [SOON + NAG_DELAY * n for n in (1, 2, 3)]
    assert len(told) == NAG_LIMIT * 2


# --- qué dice y a quién -------------------------------------------------------


def test_the_nag_goes_to_every_chat_with_only_the_done_button(parts):
    build, timer, clock, told, announced, _ = parts
    job = ring(build(), timer, clock, kind=REMINDER)
    announced.clear()

    nag(timer, clock, job)

    assert told == [
        (OWNER, "🔔 Sigue pendiente: «la pastilla»", (("✅ Hecho", f"hecho {job.id}"),)),
        (OTHER, "🔔 Sigue pendiente: «la pastilla»", (("✅ Hecho", f"hecho {job.id}"),)),
    ]
    assert announced == []


def test_a_broken_chat_does_not_stop_the_others(parts):
    build, timer, clock, *_ = parts
    reached = []

    def notify(chat_id, text, actions=()):
        if chat_id == OWNER:
            raise RuntimeError("chat roto")
        reached.append(chat_id)

    job = ring(build(notify=notify), timer, clock, kind=REMINDER)

    nag(timer, clock, job)

    assert reached == [OTHER]
    assert nag_key(job) in timer.armed


def test_without_a_list_it_nags_the_chat_that_asked(parts):
    build, timer, clock, told, *_ = parts
    job = ring(build(chat_ids=()), timer, clock, kind=REMINDER)

    nag(timer, clock, job)

    assert [chat for chat, *_ in told] == [OWNER]


# --- qué lo corta -------------------------------------------------------------


def test_done_unschedules_the_nag(parts):
    build, timer, clock, told, *_ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)

    reminders.done(OWNER, job.id, "Eze")

    assert nag_key(job) not in timer.armed


def test_a_nag_that_was_already_due_says_nothing_after_done(parts):
    build, timer, clock, told, *_ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)
    _, action = timer.armed[nag_key(job)]
    reminders.done(OWNER, job.id, "Eze")
    told.clear()

    action()

    assert told == []


def test_snoozing_closes_the_original_and_the_snoozed_one_nags_when_it_rings(parts):
    build, timer, clock, told, *_ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)

    later = reminders.snooze(OWNER, timedelta(minutes=10))

    assert nag_key(job) not in timer.armed
    assert reminders.done(OWNER, job.id, "Eze") is None
    clock.now = later.when
    timer.fire(str(later.id))
    assert timer.armed[nag_key(later)][0] == later.when + NAG_DELAY


def test_cancelling_a_reminder_that_rang_closes_the_wait(parts):
    build, timer, clock, *_ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER, repeat="daily")

    assert reminders.cancel(OWNER, job.id)

    assert nag_key(job) not in timer.armed
    assert reminders.done(OWNER, job.id, "Eze") is None


# --- después de un reinicio ---------------------------------------------------


def test_a_restart_rearms_a_pending_nag(parts):
    build, timer, clock, *_ = parts
    job = ring(build(), timer, clock, kind=REMINDER)
    timer.armed.clear()

    build().start(now=SOON + timedelta(minutes=1))

    assert timer.armed[nag_key(job)][0] == SOON + NAG_DELAY


def test_a_nag_missed_while_down_goes_out_on_start(parts):
    build, timer, clock, told, *_ = parts
    job = ring(build(), timer, clock, kind=REMINDER)
    timer.armed.clear()
    clock.now = SOON + timedelta(minutes=12)

    build().start(now=clock.now)

    assert [text for _, text, _ in told] == ["🔔 Sigue pendiente: «la pastilla»"] * 2
    assert timer.armed[nag_key(job)][0] == clock.now + NAG_DELAY


def test_a_nag_missed_past_the_window_is_dropped(parts):
    build, timer, clock, told, *_ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)
    timer.armed.clear()
    clock.now = SOON + SNOOZE_WINDOW + timedelta(minutes=1)

    build().start(now=clock.now)

    assert told == []
    assert nag_key(job) not in timer.armed
    assert reminders.done(OWNER, job.id, "Eze") == "la pastilla"


def test_a_wait_from_before_the_nags_never_nags(parts):
    """Lo que ya esperaba en una tabla sin las columnas del re-aviso no re-avisa."""
    build, timer, clock, told, _, path = parts
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE awaiting_done (job_id INTEGER PRIMARY KEY, message TEXT NOT NULL,"
        " fired_at TEXT NOT NULL);"
    )
    conn.execute(
        "INSERT INTO awaiting_done VALUES (?, ?, ?)", (7, "la pastilla", NOW.isoformat())
    )
    conn.commit()
    conn.close()

    build().start(now=NOW + timedelta(minutes=6))

    assert told == []
    assert "nag:7" not in timer.armed


# --- la tabla -----------------------------------------------------------------


def test_the_wait_counts_its_nags(tmp_path):
    awaiting = AwaitingStore(tmp_path / "jobs.db")
    awaiting.remember(1, "la pastilla", NOW, next_nag=NOW + NAG_DELAY)

    awaiting.mark_nagged(1, NOW + NAG_DELAY * 2)

    wait = awaiting.get(1)
    assert wait.message == "la pastilla"
    assert wait.fired_at == NOW
    assert wait.nags == 1
    assert wait.next_nag == NOW + NAG_DELAY * 2
    assert [w.job_id for w in awaiting.due_nags()] == [1]


def test_a_wait_without_a_next_nag_is_not_due(tmp_path):
    awaiting = AwaitingStore(tmp_path / "jobs.db")
    awaiting.remember(1, "la pastilla", NOW, next_nag=NOW + NAG_DELAY)

    awaiting.mark_nagged(1, None)

    assert awaiting.due_nags() == []
    assert awaiting.take(1) == "la pastilla"


def test_ringing_again_restarts_the_count(tmp_path):
    awaiting = AwaitingStore(tmp_path / "jobs.db")
    awaiting.remember(1, "la pastilla", NOW, next_nag=NOW + NAG_DELAY)
    awaiting.mark_nagged(1, None)

    awaiting.remember(1, "la pastilla", NOW + timedelta(days=1) - timedelta(hours=1),
                      next_nag=NOW + timedelta(days=1))

    assert awaiting.get(1).nags == 0


def test_fired_remembers_which_job_rang(tmp_path):
    fired = FiredStore(tmp_path / "jobs.db")

    fired.remember(OWNER, "la pastilla", None, NOW, REMINDER, job_id=7)

    assert fired.last(OWNER).job_id == 7


def test_an_old_fired_table_gets_the_job_column(tmp_path):
    path = tmp_path / "jobs.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE last_fired (chat_id INTEGER PRIMARY KEY, message TEXT NOT NULL,"
        " device TEXT, fired_at TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'alarm');"
    )
    conn.execute(
        "INSERT INTO last_fired (chat_id, message, fired_at) VALUES (?, ?, ?)",
        (OWNER, "arriba", NOW.isoformat()),
    )
    conn.commit()
    conn.close()

    assert FiredStore(path).last(OWNER).job_id is None

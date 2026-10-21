"""El historial de lo que sonó: una fila por aviso, con cómo terminó."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from homeauto.schedule.history import KEEP, OFF, HistoryStore
from homeauto.schedule.store import ALARM, REMINDER

OWNER = 42
NOW = datetime(2026, 10, 5, 8, 0)


@pytest.fixture
def history(tmp_path):
    return HistoryStore(tmp_path / "jobs.db")


def record(history, job_id=7, at=NOW, kind=REMINDER, message="la pastilla", repeat="daily"):
    return history.record(job_id, OWNER, kind, repeat, message, at)


def test_a_fired_job_is_kept_with_everything_it_said(history):
    record(history)

    [entry] = history.between(NOW, NOW + timedelta(minutes=1))
    assert entry.job_id == 7
    assert entry.chat_id == OWNER
    assert entry.kind == REMINDER
    assert entry.repeat == "daily"
    assert entry.message == "la pastilla"
    assert entry.fired_at == NOW
    assert not entry.announced
    assert entry.nags == 0
    assert entry.done_at is None
    assert entry.done_by is None
    assert entry.snoozed_at is None
    assert entry.closed is None
    assert entry.closed_at is None


def test_it_can_be_marked_as_said(history):
    record(history)

    history.mark_announced(7)

    [entry] = history.between(NOW, NOW + timedelta(minutes=1))
    assert entry.announced


def test_nags_add_up(history):
    record(history)

    history.mark_nag(7)
    history.mark_nag(7)

    assert history.between(NOW, NOW + timedelta(days=1))[0].nags == 2


def test_done_closes_with_who_and_when(history):
    record(history)
    at = NOW + timedelta(minutes=3)

    assert history.mark_done(7, at, "Eze")

    [entry] = history.between(NOW, NOW + timedelta(days=1))
    assert entry.done_at == at
    assert entry.done_by == "Eze"
    assert entry.closed == "done"
    assert entry.closed_at == at


def test_snooze_closes_with_when(history):
    record(history)
    at = NOW + timedelta(minutes=2)

    assert history.mark_closed(7, "snooze", at)

    [entry] = history.between(NOW, NOW + timedelta(days=1))
    assert entry.snoozed_at == at
    assert entry.closed == "snooze"
    assert entry.closed_at == at


def test_cancel_closes(history):
    record(history)

    assert history.mark_closed(7, "cancel", NOW + timedelta(minutes=2))

    [entry] = history.between(NOW, NOW + timedelta(days=1))
    assert entry.closed == "cancel"
    assert entry.closed_at == NOW + timedelta(minutes=2)
    assert entry.snoozed_at is None


def test_an_unknown_way_of_closing_is_refused(history):
    record(history)

    with pytest.raises(ValueError):
        history.mark_closed(7, "olvido", NOW)


def test_the_marks_touch_only_the_last_open_row_of_the_job(history):
    record(history, at=NOW - timedelta(days=1))
    record(history, at=NOW)
    record(history, job_id=8, at=NOW)

    history.mark_nag(7)
    history.mark_done(7, NOW + timedelta(minutes=1), "Eze")

    yesterday, today, other = history.between(NOW - timedelta(days=2), NOW + timedelta(days=1))
    assert (yesterday.nags, yesterday.closed) == (0, None)
    assert (today.nags, today.closed) == (1, "done")
    assert (other.nags, other.closed) == (0, None)


def test_a_closed_row_is_not_closed_again(history):
    record(history)
    history.mark_done(7, NOW, "Eze")

    assert not history.mark_closed(7, "cancel", NOW)
    assert not history.mark_done(7, NOW, "Ana")
    history.mark_nag(7)

    [entry] = history.between(NOW, NOW + timedelta(days=1))
    assert (entry.closed, entry.done_by, entry.nags) == ("done", "Eze", 0)


def test_a_job_that_never_fired_has_nothing_to_mark(history):
    assert not history.mark_closed(7, "cancel", NOW)
    assert not history.mark_done(7, NOW, "Eze")
    assert history.between(NOW - KEEP, NOW + KEEP) == []


def test_between_is_ordered_and_leaves_the_end_out(history):
    record(history, job_id=2, at=NOW + timedelta(hours=1))
    record(history, job_id=1, at=NOW)
    record(history, job_id=3, at=NOW + timedelta(days=1))

    entries = history.between(NOW, NOW + timedelta(days=1))

    assert [e.job_id for e in entries] == [1, 2]


def test_alarms_are_kept_too(history):
    record(history, kind=ALARM, repeat="once", message="arriba")

    assert history.between(NOW, NOW + timedelta(days=1))[0].kind == ALARM


def test_what_is_older_than_a_year_is_pruned_on_insert(history):
    assert KEEP == timedelta(days=365)
    record(history, job_id=1, at=NOW - KEEP - timedelta(days=1))
    record(history, job_id=2, at=NOW - KEEP + timedelta(days=1))

    record(history, job_id=3, at=NOW)

    entries = history.between(NOW - KEEP * 2, NOW + timedelta(days=1))
    assert [e.job_id for e in entries] == [2, 3]


def test_it_shares_the_file_with_the_other_tables(tmp_path):
    from homeauto.schedule.awaiting import AwaitingStore

    path = tmp_path / "jobs.db"
    AwaitingStore(path)
    HistoryStore(path)

    conn = sqlite3.connect(path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    assert {"awaiting_done", "fired_history"} <= tables
    assert "fired_history_fired_at" in indexes


def test_an_alarm_turned_off_keeps_who_turned_it_off(history):
    record(history, kind=ALARM, repeat="once")
    history.mark_nag(7)
    later = NOW + timedelta(minutes=3)

    assert history.mark_off(7, later, "Eze")

    [entry] = history.between(NOW, NOW + timedelta(minutes=1))
    assert entry.closed == OFF == "off"
    assert entry.done_by == "Eze"
    assert entry.closed_at == later
    assert entry.nags == 1


def test_turning_off_what_is_already_closed_says_so(history):
    record(history, kind=ALARM, repeat="once")
    history.mark_off(7, NOW, "Eze")

    assert not history.mark_off(7, NOW, "Ana")


def test_latest_are_the_last_rows_of_the_job_newest_first_without_holidays(history):
    for day in range(5):
        record(history, at=NOW + timedelta(days=day))
    record(history, job_id=8, at=NOW + timedelta(days=6))
    history.mark_closed(7, "holiday", NOW + timedelta(days=4))

    latest = history.latest(7, 3)

    assert [entry.fired_at for entry in latest] == [
        NOW + timedelta(days=3), NOW + timedelta(days=2), NOW + timedelta(days=1)
    ]


def test_latest_of_a_job_that_never_rang_is_empty(history):
    assert history.latest(7, 14) == []


# --- depurar ---


def test_count_before_counts_only_closed_rows_older_than_the_cut(history):
    record(history, job_id=1, at=NOW - timedelta(days=40))
    history.mark_done(1, NOW - timedelta(days=40), "Cin")
    record(history, job_id=2, at=NOW - timedelta(days=40))
    record(history, job_id=3, at=NOW - timedelta(days=10))
    history.mark_done(3, NOW - timedelta(days=10), "Cin")

    assert history.count_before(NOW - timedelta(days=30)) == 1


def test_delete_before_never_takes_an_open_row(history):
    record(history, job_id=1, at=NOW - timedelta(days=40))
    history.mark_done(1, NOW - timedelta(days=40), "Cin")
    record(history, job_id=2, at=NOW - timedelta(days=40))

    deleted = history.delete_before(NOW - timedelta(days=30), NOW)

    assert deleted == 1
    [left] = history.between(NOW - timedelta(days=50), NOW)
    assert left.job_id == 2
    assert left.closed is None


def test_delete_before_leaves_a_row_closed_after_it_was_shown(history):
    record(history, job_id=2, at=NOW - timedelta(days=40))
    history.mark_closed(2, "cancel", NOW + timedelta(minutes=1))

    assert history.delete_before(NOW - timedelta(days=30), NOW) == 0
    assert len(history.between(NOW - timedelta(days=50), NOW)) == 1


def test_a_row_keeps_the_assignment_and_who_it_reached(history):
    history.record(
        7, OWNER, REMINDER, "daily", "la pastilla", NOW,
        assignee="person", assignee_id=3, audience=(OWNER,),
    )

    [entry] = history.between(NOW, NOW + timedelta(minutes=1))
    assert (entry.assignee, entry.assignee_id, entry.audience) == ("person", 3, (OWNER,))


def test_by_default_a_row_is_for_nobody_and_reached_everyone(history):
    record(history)

    [entry] = history.between(NOW, NOW + timedelta(minutes=1))
    assert (entry.assignee, entry.assignee_id, entry.audience) == ("none", None, None)


def test_an_old_table_gets_the_assignment_columns(tmp_path):
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE fired_history (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER,"
            " chat_id INTEGER, kind TEXT NOT NULL, repeat TEXT NOT NULL DEFAULT 'once',"
            " message TEXT NOT NULL, fired_at TEXT NOT NULL, announced INTEGER NOT NULL DEFAULT 0,"
            " done_at TEXT, done_by TEXT, nags INTEGER NOT NULL DEFAULT 0, snoozed_at TEXT,"
            " closed TEXT, closed_at TEXT)"
        )
        conn.execute(
            "INSERT INTO fired_history (job_id, chat_id, kind, message, fired_at)"
            " VALUES (7, ?, 'reminder', 'la pastilla', ?)",
            (OWNER, NOW.isoformat()),
        )

    [entry] = HistoryStore(path).between(NOW, NOW + timedelta(minutes=1))

    assert (entry.assignee, entry.assignee_id, entry.audience) == ("none", None, None)

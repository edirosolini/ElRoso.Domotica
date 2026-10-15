from datetime import datetime, timedelta

from homeauto.schedule.history import CANCEL, SNOOZE, HistoryStore
from homeauto.schedule.reminders import RING_LIMIT
from homeauto.weekly import MAX_LINES, Weekly

# Domingo a las siete de la tarde, la hora por defecto del resumen.
NOW = datetime(2026, 10, 11, 19, 0)


def at(days_ago: int, hour: int = 8, minute: int = 0) -> datetime:
    return (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=minute)


def weekly(tmp_path):
    history = HistoryStore(tmp_path / "jobs.db")
    return history, Weekly(history=history, clock=lambda: NOW)


def fire(history, job_id, kind, repeat, message, when, announced=True):
    history.record(job_id, 42, kind, repeat, message, when)
    if announced:
        history.mark_announced(job_id)


def test_an_empty_week_says_nothing(tmp_path):
    _, summary = weekly(tmp_path)

    assert summary.text() == ""


def test_a_daily_reminder_counts_the_days_it_was_done(tmp_path):
    history, summary = weekly(tmp_path)
    for days_ago in range(7):
        fire(history, 5, "reminder", "daily", "Medicación de Die", at(days_ago))
        if days_ago != 3:
            history.mark_done(5, at(days_ago, 8, 5), "Eze")

    assert "Medicación de Die: 6 de 7" in summary.text()


def test_a_postponed_reminder_done_later_counts_for_its_day(tmp_path):
    history, summary = weekly(tmp_path)
    fire(history, 5, "reminder", "daily", "la pastilla", at(1))
    history.mark_closed(5, SNOOZE, at(1, 8, 2))
    fire(history, 9, "reminder", "once", "la pastilla", at(1, 8, 12))
    history.mark_done(9, at(1, 8, 13), "Eze")
    fire(history, 5, "reminder", "daily", "la pastilla", at(0))

    assert "la pastilla: 1 de 2" in summary.text()


def test_a_day_counts_once_however_many_times_it_rang(tmp_path):
    history, summary = weekly(tmp_path)
    fire(history, 5, "reminder", "weekly", "regar", at(2))
    history.mark_closed(5, SNOOZE, at(2, 8, 1))
    fire(history, 9, "reminder", "once", "regar", at(2, 8, 11))
    history.mark_closed(9, SNOOZE, at(2, 8, 12))
    fire(history, 10, "reminder", "once", "regar", at(2, 8, 22))

    assert "regar: 0 de 1" in summary.text()


def test_a_long_message_is_cut(tmp_path):
    history, summary = weekly(tmp_path)
    message = "Tomar la pastilla de la presión antes del desayuno con agua"
    fire(history, 5, "reminder", "daily", message, at(1))

    text = summary.text()

    assert message not in text
    assert message[:30] in text
    assert ": 0 de 1" in text


def test_a_timer_is_left_out(tmp_path):
    history, summary = weekly(tmp_path)
    fire(history, 5, "reminder", "once", "sacar la pizza", at(1), announced=False)
    history.mark_nag(5)

    assert summary.text() == ""


def test_an_alarm_nobody_turned_off_is_counted(tmp_path):
    history, summary = weekly(tmp_path)
    fire(history, 3, "alarm", "daily", "arriba", at(2, 7, 30))
    history.mark_nag(3)

    text = summary.text()

    assert "nadie apagó" in text
    assert "arriba" in text


def test_an_alarm_turned_off_is_not_counted(tmp_path):
    history, summary = weekly(tmp_path)
    fire(history, 3, "alarm", "daily", "arriba", at(2, 7, 30))
    history.mark_nag(3)
    history.mark_off(3, at(2, 7, 35), "Eze")

    assert summary.text() == ""


def test_an_alarm_that_rang_once_and_stopped_is_not_counted(tmp_path):
    history, summary = weekly(tmp_path)
    fire(history, 3, "alarm", "once", "arriba", at(2, 7, 30))

    assert summary.text() == ""


def test_an_alarm_still_ringing_is_not_counted(tmp_path):
    history, summary = weekly(tmp_path)
    fire(history, 3, "alarm", "once", "arriba", NOW - RING_LIMIT + timedelta(minutes=1))
    history.mark_nag(3)

    assert summary.text() == ""


def test_what_did_not_come_out_of_the_speaker_is_counted(tmp_path):
    history, summary = weekly(tmp_path)
    fire(history, 3, "alarm", "once", "arriba", at(4, 7, 30), announced=False)
    history.mark_off(3, at(4, 7, 31), "Eze")

    text = summary.text()

    assert "parlante" in text
    assert "arriba" in text


def test_what_rang_eight_days_ago_is_left_out(tmp_path):
    history, summary = weekly(tmp_path)
    fire(history, 5, "reminder", "daily", "la pastilla", at(8))
    fire(history, 3, "alarm", "daily", "arriba", at(8, 7, 30), announced=False)
    history.mark_nag(3)
    fire(history, 5, "reminder", "daily", "la pastilla", at(6))
    history.mark_done(5, at(6, 8, 1), "Eze")

    text = summary.text()

    assert "la pastilla: 1 de 1" in text
    assert "arriba" not in text


def test_a_cancelled_reminder_still_counts_its_day(tmp_path):
    history, summary = weekly(tmp_path)
    fire(history, 5, "reminder", "daily", "la pastilla", at(1))
    history.mark_closed(5, CANCEL, at(1, 9))

    assert "la pastilla: 0 de 1" in summary.text()


def test_a_long_list_is_capped(tmp_path):
    history, summary = weekly(tmp_path)
    for job_id in range(MAX_LINES + 3):
        fire(history, job_id, "alarm", "once", f"alarma {job_id}", at(1, 7, job_id), announced=False)

    text = summary.text()

    assert f"No salieron por el parlante: {MAX_LINES + 3}" in text
    assert "… y 3 más" in text


"""Lo programado en un rango: lo que va a sonar y lo que ya sonó."""

from datetime import date, datetime, timedelta

from homeauto.schedule.history import CANCEL, DONE, OFF, SNOOZE, Entry
from homeauto.schedule.month import (
    ALARM_ITEM,
    REMINDER_ITEM,
    TIMER_ITEM,
    from_history,
    occurrences_between,
)
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import (
    ALARM, DAILY, MONTHLY, ONCE, REMINDER, WEEKLY, Job, Store, next_run,
)

NOW = datetime(2026, 10, 5, 12, 0)  # lunes
OCTOBER = (datetime(2026, 10, 1), datetime(2026, 11, 1))


def october(jobs, now=NOW):
    return occurrences_between(jobs, *OCTOBER, now)


def job(when, repeat=ONCE, days=None, kind=ALARM, message="arriba", job_id=1, monthday=None):
    return Job(
        id=job_id, chat_id=42, when=when, message=message, repeat=repeat, days=days, kind=kind,
        monthday=monthday,
    )


def entry(at, kind=ALARM, repeat=ONCE, message="arriba", announced=True, **marks):
    return Entry(
        id=1,
        job_id=1,
        chat_id=42,
        kind=kind,
        repeat=repeat,
        message=message,
        fired_at=at,
        announced=announced,
        done_at=marks.get("done_at"),
        done_by=marks.get("done_by"),
        nags=marks.get("nags", 0),
        snoozed_at=marks.get("snoozed_at"),
        closed=marks.get("closed"),
    )


# --- la regla de repetición ---


def test_a_one_shot_does_not_come_back():
    assert next_run(job(NOW), NOW) is None


def test_a_daily_comes_back_the_next_day():
    assert next_run(job(NOW, DAILY), NOW) == NOW + timedelta(days=1)


def test_a_weekly_jumps_to_the_next_marked_day():
    weekly = job(NOW, WEEKLY, days="1,3")

    assert next_run(weekly, NOW) == datetime(2026, 10, 7, 12, 0)


def test_a_weekly_from_friday_to_monday_wraps_around():
    friday = datetime(2026, 10, 9, 7, 0)
    weekly = job(friday, WEEKLY, days="1,5,6,7")

    assert next_run(weekly, friday) == datetime(2026, 10, 10, 7, 0)
    assert next_run(weekly, datetime(2026, 10, 11, 7, 0)) == datetime(2026, 10, 12, 7, 0)


def test_a_monthly_comes_back_the_same_day_next_month():
    monthly = job(datetime(2026, 10, 10, 9, 0), MONTHLY, monthday=10)

    assert next_run(monthly, monthly.when) == datetime(2026, 11, 10, 9, 0)


def test_a_monthly_crosses_the_year():
    monthly = job(datetime(2026, 12, 10, 9, 0), MONTHLY, monthday=10)

    assert next_run(monthly, monthly.when) == datetime(2027, 1, 10, 9, 0)


def test_a_monthly_on_a_missing_day_falls_on_the_last_one_and_keeps_its_day():
    monthly = job(datetime(2027, 1, 31, 9, 0), MONTHLY, monthday=31)

    february = next_run(monthly, monthly.when)
    march = next_run(monthly, february)
    april = next_run(monthly, march)

    assert february == datetime(2027, 2, 28, 9, 0)
    assert march == datetime(2027, 3, 31, 9, 0)
    assert april == datetime(2027, 4, 30, 9, 0)


def test_a_monthly_on_the_thirty_first_lands_on_a_leap_february_twenty_ninth():
    monthly = job(datetime(2028, 1, 31, 9, 0), MONTHLY, monthday=31)

    assert next_run(monthly, monthly.when) == datetime(2028, 2, 29, 9, 0)


class _Timer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)


def test_the_screen_and_the_reminders_follow_the_same_rule(tmp_path):
    """Lo que la pantalla dice que va a sonar es lo que Reminders rearma después de sonar."""
    store = Store(tmp_path / "jobs.db")
    timer = _Timer()
    reminders = Reminders(store=store, timer=timer, announce=lambda job: None, clock=lambda: NOW)
    friday = datetime(2026, 10, 9, 7, 0)
    added = reminders.add(42, friday, "colegio", repeat=WEEKLY, days=[5, 6, 7, 1])

    expected = [item.at for item in october([added])]
    fired = [added.when]
    for _ in range(len(expected) - 1):
        timer.armed[str(added.id)][1]()
        fired.append(store.get(added.id).when)

    assert fired == expected



def test_the_screen_and_the_reminders_follow_the_same_monthly_rule(tmp_path):
    """Lo mensual en la pantalla es lo que Reminders rearma, también en los meses cortos."""
    store = Store(tmp_path / "jobs.db")
    timer = _Timer()
    reminders = Reminders(store=store, timer=timer, announce=lambda job: None, clock=lambda: NOW)
    added = reminders.add(42, datetime(2026, 10, 31, 9, 0), "luz", repeat=MONTHLY, monthday=31)

    expected = [
        item.at
        for item in occurrences_between([added], datetime(2026, 10, 1), datetime(2027, 5, 1), NOW)
    ]
    fired = [added.when]
    for _ in range(len(expected) - 1):
        timer.armed[str(added.id)][1]()
        fired.append(store.get(added.id).when)

    assert fired == expected

# --- la expansión de lo programado ---


def test_a_daily_fills_the_rest_of_the_range_from_now():
    daily = job(datetime(2026, 10, 5, 21, 0), DAILY)

    found = october([daily])

    assert [item.at.day for item in found] == list(range(5, 32))
    assert all(item.at.hour == 21 for item in found)


def test_what_already_passed_is_not_expanded():
    daily = job(datetime(2026, 10, 6, 8, 0), DAILY)

    found = october([daily], datetime(2026, 10, 20, 9, 0))

    assert found[0].at == datetime(2026, 10, 21, 8, 0)


def test_a_weekly_only_lands_on_its_days():
    weekly = job(datetime(2026, 10, 9, 7, 0), WEEKLY, days="1,5,6,7")

    found = october([weekly])

    assert {item.at.isoweekday() for item in found} == {1, 5, 6, 7}
    assert found[0].at == datetime(2026, 10, 9, 7, 0)


def test_a_monthly_lands_once_in_the_month():
    monthly = job(datetime(2026, 10, 10, 9, 0), MONTHLY, monthday=10)

    assert [item.at for item in october([monthly])] == [datetime(2026, 10, 10, 9, 0)]


def test_a_monthly_that_started_long_ago_is_found_in_a_later_range():
    monthly = job(datetime(2026, 10, 31, 9, 0), MONTHLY, monthday=31)

    found = occurrences_between([monthly], datetime(2027, 2, 1), datetime(2027, 5, 1), NOW)

    assert [item.at for item in found] == [
        datetime(2027, 2, 28, 9, 0), datetime(2027, 3, 31, 9, 0), datetime(2027, 4, 30, 9, 0),
    ]


def test_a_monthly_whose_day_already_passed_in_the_range_waits_for_the_next_month():
    monthly = job(datetime(2026, 10, 10, 9, 0), MONTHLY, monthday=10)

    found = occurrences_between([monthly], datetime(2026, 11, 15), datetime(2027, 1, 1), NOW)

    assert [item.at for item in found] == [datetime(2026, 12, 10, 9, 0)]


def test_a_range_far_ahead_is_expanded_too():
    daily = job(datetime(2026, 10, 6, 8, 0), DAILY)

    found = occurrences_between([daily], datetime(2030, 2, 1), datetime(2030, 3, 1), NOW)

    assert len(found) == 28
    assert found[0].at == datetime(2030, 2, 1, 8, 0)


def test_a_one_shot_outside_the_range_is_left_out():
    assert october([job(datetime(2026, 11, 1, 8, 0))]) == []


def test_alarm_reminder_and_timer_are_told_apart():
    kinds = [
        item.kind
        for item in october(
            [
                job(datetime(2026, 10, 6, 8, 0), DAILY, kind=ALARM, job_id=1),
                job(datetime(2026, 10, 6, 9, 0), WEEKLY, days="2", kind=REMINDER, job_id=2),
                job(datetime(2026, 10, 6, 10, 0), ONCE, kind=REMINDER, job_id=3),
            ],
            datetime(2026, 10, 6, 7, 0),
        )
        if item.at.day == 6
    ]

    assert kinds == [ALARM_ITEM, REMINDER_ITEM, TIMER_ITEM]


def test_a_snoozed_reminder_reads_as_a_timer_until_it_sounds():
    snoozed = job(datetime(2026, 10, 5, 12, 30), ONCE, kind=REMINDER)

    [item] = october([snoozed])

    assert item.kind == TIMER_ITEM


def test_a_range_expands_the_daily_across_two_months():
    daily = job(datetime(2026, 10, 6, 8, 0), DAILY)

    found = occurrences_between([daily], datetime(2026, 10, 26), datetime(2026, 11, 9), NOW)

    assert [item.at.date() for item in found] == [
        date(2026, 10, 26) + timedelta(days=offset) for offset in range(14)
    ]


def test_a_range_starts_at_now_when_now_is_inside():
    daily = job(datetime(2026, 10, 5, 8, 0), DAILY)

    found = occurrences_between([daily], datetime(2026, 10, 5), datetime(2026, 10, 7), NOW)

    assert [item.at for item in found] == [datetime(2026, 10, 6, 8, 0)]


def test_a_range_end_is_left_out():
    once = job(datetime(2026, 10, 7, 0, 0))

    assert occurrences_between([once], datetime(2026, 10, 6), datetime(2026, 10, 7), NOW) == []


def test_a_range_in_the_past_has_nothing_scheduled():
    daily = job(datetime(2026, 10, 6, 8, 0), DAILY)

    assert occurrences_between([daily], datetime(2026, 9, 1), datetime(2026, 10, 1), NOW) == []


# --- lo que ya sonó ---


def test_a_history_entry_becomes_a_past_item():
    at = datetime(2026, 10, 2, 8, 0)

    item = from_history(entry(at, kind=REMINDER, repeat=DAILY, done_by="Eze", closed=DONE))

    assert item.past and item.done and item.done_by == "Eze" and item.kind == REMINDER_ITEM


def test_the_history_keeps_how_each_one_ended():
    at = datetime(2026, 10, 2, 8, 0)
    done, snoozed, cancelled, silent = [
        from_history(e)
        for e in (
            entry(at, kind=REMINDER, repeat=DAILY, done_by="Eze", done_at=at, closed=DONE, nags=2),
            entry(at, kind=REMINDER, repeat=DAILY, closed=SNOOZE, snoozed_at=at),
            entry(at, closed=CANCEL),
            entry(at, announced=False),
        )
    ]

    assert done.done and done.done_by == "Eze" and done.nags == 2
    assert snoozed.snoozed and not snoozed.done
    assert cancelled.cancelled
    assert silent.silent and not done.silent


def test_an_alarm_turned_off_shows_as_off():
    at = datetime(2026, 10, 2, 8, 0)

    item = from_history(entry(at, closed=OFF, done_by="Eze", nags=3))

    assert item.off and item.done_by == "Eze" and item.nags == 3
    assert not item.done and not item.cancelled

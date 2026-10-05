"""El mes de lo programado: lo que va a sonar y lo que ya sonó."""

from datetime import date, datetime, timedelta

from homeauto.schedule.history import CANCEL, DONE, SNOOZE, Entry
from homeauto.schedule.month import (
    ALARM_ITEM,
    REMINDER_ITEM,
    TIMER_ITEM,
    month_view,
    occurrences,
)
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import ALARM, DAILY, ONCE, REMINDER, WEEKLY, Job, Store, next_run

NOW = datetime(2026, 10, 5, 12, 0)  # lunes


def job(when, repeat=ONCE, days=None, kind=ALARM, message="arriba", job_id=1):
    return Job(id=job_id, chat_id=42, when=when, message=message, repeat=repeat, days=days, kind=kind)


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


class _Timer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)


def test_the_page_and_the_reminders_follow_the_same_rule(tmp_path):
    """Lo que la página dice que va a sonar es lo que Reminders rearma después de sonar."""
    store = Store(tmp_path / "jobs.db")
    timer = _Timer()
    reminders = Reminders(store=store, timer=timer, announce=lambda job: None, clock=lambda: NOW)
    friday = datetime(2026, 10, 9, 7, 0)
    added = reminders.add(42, friday, "colegio", repeat=WEEKLY, days=[5, 6, 7, 1])

    expected = [item.at for item in occurrences([added], 2026, 10, NOW)]
    fired = [added.when]
    for _ in range(len(expected) - 1):
        timer.armed[str(added.id)][1]()
        fired.append(store.get(added.id).when)

    assert fired == expected


# --- la expansión de lo programado ---


def test_a_daily_fills_the_rest_of_the_month_from_now():
    daily = job(datetime(2026, 10, 5, 21, 0), DAILY)

    found = occurrences([daily], 2026, 10, NOW)

    assert [item.at.day for item in found] == list(range(5, 32))
    assert all(item.at.hour == 21 for item in found)


def test_what_already_passed_is_not_expanded():
    daily = job(datetime(2026, 10, 6, 8, 0), DAILY)

    found = occurrences([daily], 2026, 10, datetime(2026, 10, 20, 9, 0))

    assert found[0].at == datetime(2026, 10, 21, 8, 0)


def test_a_weekly_only_lands_on_its_days():
    weekly = job(datetime(2026, 10, 9, 7, 0), WEEKLY, days="1,5,6,7")

    found = occurrences([weekly], 2026, 10, NOW)

    assert {item.at.isoweekday() for item in found} == {1, 5, 6, 7}
    assert found[0].at == datetime(2026, 10, 9, 7, 0)


def test_a_month_far_ahead_is_expanded_too():
    daily = job(datetime(2026, 10, 6, 8, 0), DAILY)

    found = occurrences([daily], 2030, 2, NOW)

    assert len(found) == 28
    assert found[0].at == datetime(2030, 2, 1, 8, 0)


def test_a_one_shot_outside_the_month_is_left_out():
    assert occurrences([job(datetime(2026, 11, 1, 8, 0))], 2026, 10, NOW) == []


def test_a_past_month_has_nothing_scheduled():
    daily = job(datetime(2026, 10, 6, 8, 0), DAILY)

    assert occurrences([daily], 2026, 9, NOW) == []


def test_alarm_reminder_and_timer_are_told_apart():
    kinds = [
        item.kind
        for item in occurrences(
            [
                job(datetime(2026, 10, 6, 8, 0), DAILY, kind=ALARM, job_id=1),
                job(datetime(2026, 10, 6, 9, 0), WEEKLY, days="2", kind=REMINDER, job_id=2),
                job(datetime(2026, 10, 6, 10, 0), ONCE, kind=REMINDER, job_id=3),
            ],
            2026,
            10,
            datetime(2026, 10, 6, 7, 0),
        )
        if item.at.day == 6
    ]

    assert kinds == [ALARM_ITEM, REMINDER_ITEM, TIMER_ITEM]


# --- la vista del mes ---


def test_the_grid_starts_on_monday_and_has_whole_weeks():
    view = month_view([], [], 2026, 10, NOW)

    assert all(len(week) == 7 for week in view.weeks)
    assert view.weeks[0][0].date == date(2026, 9, 28)
    assert view.weeks[-1][-1].date == date(2026, 11, 1)
    assert not view.weeks[0][0].in_month
    assert view.weeks[0][3].date == date(2026, 10, 1)


def test_the_view_knows_today_and_its_neighbours():
    view = month_view([], [], 2026, 1, datetime(2026, 1, 15, 9, 0))

    assert [day.date for week in view.weeks for day in week if day.today] == [date(2026, 1, 15)]
    assert view.previous == (2025, 12)
    assert view.following == (2026, 2)


def test_today_mixes_what_sounded_with_what_is_coming_without_repeating():
    rearmed = job(datetime(2026, 10, 6, 8, 0), DAILY)
    later = job(datetime(2026, 10, 5, 18, 0), job_id=2, message="la pizza")
    sounded = entry(datetime(2026, 10, 5, 8, 0), repeat=DAILY)

    view = month_view([rearmed, later], [sounded], 2026, 10, NOW)

    [today] = [day for day in view.days if day.date == date(2026, 10, 5)]
    assert [(item.at.hour, item.past) for item in today.items] == [(8, True), (18, False)]


def test_history_after_now_is_ignored():
    view = month_view([], [entry(NOW + timedelta(hours=1))], 2026, 10, NOW)

    assert view.days == []


def test_a_past_month_shows_only_the_history():
    daily = job(datetime(2026, 10, 6, 8, 0), DAILY)
    old = entry(datetime(2026, 9, 10, 8, 0))

    view = month_view([daily], [old], 2026, 9, NOW)

    assert [(day.date, len(day.items)) for day in view.days] == [(date(2026, 9, 10), 1)]


def test_the_history_keeps_how_each_one_ended():
    at = datetime(2026, 10, 2, 8, 0)
    entries = [
        entry(at, kind=REMINDER, repeat=DAILY, done_by="Eze", done_at=at, closed=DONE, nags=2),
        entry(at, kind=REMINDER, repeat=DAILY, closed=SNOOZE, snoozed_at=at),
        entry(at, closed=CANCEL),
        entry(at, announced=False),
    ]

    [day] = month_view([], entries, 2026, 10, NOW).days
    done, snoozed, cancelled, silent = day.items

    assert done.done and done.done_by == "Eze" and done.nags == 2
    assert snoozed.snoozed and not snoozed.done
    assert cancelled.cancelled
    assert silent.silent and not done.silent


def test_a_snoozed_reminder_reads_as_a_timer_until_it_sounds():
    snoozed = job(datetime(2026, 10, 5, 12, 30), ONCE, kind=REMINDER)

    [item] = occurrences([snoozed], 2026, 10, NOW)

    assert item.kind == TIMER_ITEM

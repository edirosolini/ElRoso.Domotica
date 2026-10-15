"""Las reglas de lo programado, compartidas por el chat y la pantalla."""

from datetime import datetime, timedelta

import pytest

from homeauto.schedule.month import ALARM_ITEM, REMINDER_ITEM, TIMER_ITEM
from homeauto.schedule.spec import (
    SpecError, classify, repetition_label, resolve, ringing_label, short_month_note,
)
from homeauto.schedule.store import ALARM, DAILY, MONTHLY, ONCE, REMINDER, WEEKLY, Job

# Un lunes.
NOW = datetime(2026, 10, 5, 12, 0)


@pytest.mark.parametrize(
    ("item", "repeat", "expected"),
    [
        (TIMER_ITEM, ONCE, (REMINDER, ONCE)),
        (REMINDER_ITEM, DAILY, (REMINDER, DAILY)),
        (REMINDER_ITEM, WEEKLY, (REMINDER, WEEKLY)),
        (ALARM_ITEM, ONCE, (ALARM, ONCE)),
        (ALARM_ITEM, DAILY, (ALARM, DAILY)),
        (ALARM_ITEM, WEEKLY, (ALARM, WEEKLY)),
        (ALARM_ITEM, MONTHLY, (ALARM, MONTHLY)),
        (REMINDER_ITEM, MONTHLY, (REMINDER, MONTHLY)),
    ],
)
def test_each_screen_type_is_a_kind_and_a_repetition(item, repeat, expected):
    assert classify(item, repeat) == expected


def test_a_reminder_without_days_is_refused():
    with pytest.raises(SpecError, match="recordatorio repite"):
        classify(REMINDER_ITEM, ONCE)


@pytest.mark.parametrize("repeat", [DAILY, WEEKLY, MONTHLY])
def test_a_timer_only_rings_once(repeat):
    with pytest.raises(SpecError, match="una sola vez"):
        classify(TIMER_ITEM, repeat)


@pytest.mark.parametrize(("item", "repeat"), [("despertador", ONCE), (ALARM_ITEM, "yearly")])
def test_unknown_types_and_repetitions_are_refused(item, repeat):
    with pytest.raises(SpecError):
        classify(item, repeat)


def test_once_in_the_future_stays_as_is():
    when = NOW + timedelta(hours=1)

    assert resolve(ONCE, when, NOW) == when


@pytest.mark.parametrize("when", [NOW, NOW - timedelta(minutes=1)])
def test_once_in_the_past_is_refused(when):
    with pytest.raises(SpecError, match="ya pasó"):
        resolve(ONCE, when, NOW)


def test_daily_in_the_past_rolls_to_its_next_occurrence():
    assert resolve(DAILY, datetime(2026, 10, 1, 7, 30), NOW) == datetime(2026, 10, 6, 7, 30)


def test_daily_later_today_stays_today():
    assert resolve(DAILY, datetime(2026, 10, 5, 20, 0), NOW) == datetime(2026, 10, 5, 20, 0)


def test_weekly_goes_to_the_first_marked_day():
    # Miércoles y viernes, desde un lunes.
    assert resolve(WEEKLY, datetime(2026, 10, 5, 13, 0), NOW, (3, 5)) == datetime(
        2026, 10, 7, 13, 0
    )


def test_weekly_in_the_past_rolls_before_choosing_the_day():
    # Un lunes a una hora que ya pasó: el lunes que viene.
    assert resolve(WEEKLY, datetime(2026, 10, 5, 7, 0), NOW, (1,)) == datetime(2026, 10, 12, 7, 0)


@pytest.mark.parametrize("days", [None, (), (0,), (8,)])
def test_weekly_needs_valid_days(days):
    with pytest.raises(SpecError):
        resolve(WEEKLY, datetime(2026, 10, 6, 7, 0), NOW, days)


def test_monthly_later_this_month_stays_this_month():
    assert resolve(MONTHLY, datetime(2026, 10, 5, 9, 0), NOW, monthday=20) == datetime(
        2026, 10, 20, 9, 0
    )


def test_monthly_on_a_day_already_gone_goes_to_next_month():
    """Hoy es 15 y se pide el 10: el 10 del mes que viene."""
    now = datetime(2026, 10, 15, 12, 0)

    assert resolve(MONTHLY, datetime(2026, 10, 16, 9, 0), now, monthday=10) == datetime(
        2026, 11, 10, 9, 0
    )


def test_monthly_today_at_an_hour_that_passed_goes_to_next_month():
    assert resolve(MONTHLY, datetime(2026, 10, 6, 9, 0), NOW, monthday=5) == datetime(
        2026, 11, 5, 9, 0
    )


def test_monthly_on_a_day_this_month_lacks_falls_on_its_last_day():
    now = datetime(2027, 2, 3, 12, 0)

    assert resolve(MONTHLY, datetime(2027, 2, 4, 9, 0), now, monthday=31) == datetime(
        2027, 2, 28, 9, 0
    )


@pytest.mark.parametrize("monthday", [None, 0, 32])
def test_monthly_needs_a_day_that_exists(monthday):
    with pytest.raises(SpecError):
        resolve(MONTHLY, datetime(2026, 10, 6, 9, 0), NOW, monthday=monthday)


def label_of(repeat, days=None, monthday=None):
    return repetition_label(
        Job(id=1, chat_id=42, when=NOW, message="x", repeat=repeat, days=days, monthday=monthday)
    )


def test_the_repetition_is_told_in_one_place():
    assert label_of(ONCE) == ""
    assert label_of(DAILY) == "todos los días"
    assert label_of(WEEKLY, days="1,3") == "lun, mié"
    assert label_of(MONTHLY, monthday=10) == "el 10 de cada mes"


@pytest.mark.parametrize("monthday", [1, 10, 28])
def test_a_day_every_month_has_needs_no_note(monthday):
    assert short_month_note(monthday) == ""


@pytest.mark.parametrize("monthday", [29, 30, 31])
def test_a_day_some_months_lack_says_what_happens(monthday):
    assert short_month_note(monthday) == f"Los meses que no tienen {monthday}, el último día."


def ringing_of(repeat, days=None, monthday=None):
    return ringing_label(
        Job(id=1, chat_id=42, when=NOW, message="x", repeat=repeat, days=days, monthday=monthday)
    )


def test_the_repetition_when_it_rings_has_no_digits():
    assert ringing_of(ONCE) == ""
    assert ringing_of(DAILY) == "de todos los días"
    assert ringing_of(WEEKLY, days="1,3") == "de lun, mié"
    assert ringing_of(MONTHLY, monthday=10) == "del diez de cada mes"
    assert ringing_of(MONTHLY, monthday=31) == "del treinta y uno de cada mes"
    assert ringing_of(MONTHLY, monthday=1) == "del uno de cada mes"

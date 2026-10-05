"""Las reglas de lo programado, compartidas por el chat y la pantalla."""

from datetime import datetime, timedelta

import pytest

from homeauto.schedule.month import ALARM_ITEM, REMINDER_ITEM, TIMER_ITEM
from homeauto.schedule.spec import SpecError, classify, resolve
from homeauto.schedule.store import ALARM, DAILY, ONCE, REMINDER, WEEKLY

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
    ],
)
def test_each_screen_type_is_a_kind_and_a_repetition(item, repeat, expected):
    assert classify(item, repeat) == expected


def test_a_reminder_without_days_is_refused():
    with pytest.raises(SpecError, match="recordatorio repite"):
        classify(REMINDER_ITEM, ONCE)


@pytest.mark.parametrize("repeat", [DAILY, WEEKLY])
def test_a_timer_only_rings_once(repeat):
    with pytest.raises(SpecError, match="una sola vez"):
        classify(TIMER_ITEM, repeat)


@pytest.mark.parametrize(("item", "repeat"), [("despertador", ONCE), (ALARM_ITEM, "monthly")])
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

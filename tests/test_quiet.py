from datetime import datetime, time

import pytest

from homeauto.quiet import QuietHours

# La ventana cruza la medianoche, que es el caso que se rompe solo.
NIGHT = QuietHours(start=time(23, 0), end=time(7, 0))


def at(hour, minute=0):
    return datetime(2026, 8, 30, hour, minute)


@pytest.mark.parametrize("moment", [at(23, 0), at(23, 30), at(0, 0), at(3, 15), at(6, 59)])
def test_inside_the_night_window(moment):
    assert NIGHT.is_quiet(moment) is True


@pytest.mark.parametrize("moment", [at(7, 0), at(7, 1), at(12), at(22, 59)])
def test_outside_the_night_window(moment):
    assert NIGHT.is_quiet(moment) is False


def test_a_window_inside_the_same_day():
    siesta = QuietHours(start=time(13, 0), end=time(15, 0))

    assert siesta.is_quiet(at(14)) is True
    assert siesta.is_quiet(at(12, 59)) is False
    assert siesta.is_quiet(at(15, 0)) is False


def test_equal_bounds_mean_no_quiet_hours_at_all():
    always = QuietHours(start=time(0, 0), end=time(0, 0))

    assert always.is_quiet(at(3)) is False
    assert always.enabled is False


def test_it_says_the_window_out_loud_for_the_reply():
    assert "23:00" in NIGHT.label and "07:00" in NIGHT.label


def test_parses_from_text():
    parsed = QuietHours.parse("23:00", "07:00")

    assert parsed.start == time(23, 0)
    assert parsed.end == time(7, 0)


def test_rejects_nonsense():
    with pytest.raises(ValueError):
        QuietHours.parse("veintitrés", "07:00")
    with pytest.raises(ValueError):
        QuietHours.parse("25:00", "07:00")

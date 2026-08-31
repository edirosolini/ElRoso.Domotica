"""Silencio a pedido: callar un rato sin tocar el horario de descanso."""

from datetime import datetime, timedelta

import pytest

from homeauto.quiet import Hush, HushStore, QuietHours

HOURS = QuietHours.parse("23:00", "07:00")
NOON = datetime(2026, 8, 31, 12, 0)


@pytest.fixture
def hush(tmp_path):
    moment = [NOON]
    silence = Hush(hours=HOURS, store=HushStore(tmp_path / "jobs.db"), clock=lambda: moment[0])
    silence.now = moment  # el test mueve el reloj
    return silence


def test_nothing_asked_means_the_usual_hours(hush):
    assert hush.is_quiet(NOON) is False
    assert hush.is_quiet(datetime(2026, 8, 31, 23, 30)) is True


def test_asking_for_silence_shuts_the_house_up(hush):
    hush.start(timedelta(hours=2))

    assert hush.is_quiet(NOON) is True


def test_the_silence_says_when_it_ends(hush):
    assert hush.start(timedelta(hours=2)) == datetime(2026, 8, 31, 14, 0)
    assert hush.until() == datetime(2026, 8, 31, 14, 0)


def test_once_the_time_is_up_the_house_talks_again(hush):
    hush.start(timedelta(hours=2))

    hush.now[0] = datetime(2026, 8, 31, 14, 1)

    assert hush.is_quiet(hush.now[0]) is False
    assert hush.until() is None


def test_it_can_be_cut_short(hush):
    hush.start(timedelta(hours=2))

    assert hush.stop() is True
    assert hush.is_quiet(NOON) is False


def test_stopping_a_silence_nobody_asked_for_says_so(hush):
    assert hush.stop() is False


def test_the_resting_hours_still_win_after_the_silence_ends(hush):
    hush.start(timedelta(minutes=10))
    hush.now[0] = datetime(2026, 9, 1, 2, 0)

    assert hush.is_quiet(hush.now[0]) is True


def test_the_label_explains_which_rule_is_talking(hush):
    assert hush.label == HOURS.label

    hush.start(timedelta(hours=2))

    assert "14:00" in hush.label
    assert "pedido" in hush.label


def test_the_silence_survives_a_restart(tmp_path):
    store = lambda: HushStore(tmp_path / "jobs.db")
    Hush(hours=HOURS, store=store(), clock=lambda: NOON).start(timedelta(hours=2))

    revived = Hush(hours=HOURS, store=store(), clock=lambda: NOON)

    assert revived.is_quiet(NOON) is True


def test_a_new_silence_replaces_the_one_before(hush):
    hush.start(timedelta(hours=2))
    hush.start(timedelta(minutes=30))

    assert hush.until() == datetime(2026, 8, 31, 12, 30)

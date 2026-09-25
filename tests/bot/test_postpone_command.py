from datetime import datetime, timedelta

import pytest

from homeauto.bot.commands import HELP, Commands
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import Store

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
STRANGER = 99
NOW = datetime(2026, 9, 25, 7, 31)
FIRED = datetime(2026, 9, 25, 7, 30)


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)


@pytest.fixture
def cmd(tmp_path):
    path = tmp_path / "jobs.db"
    fired = FiredStore(path)
    reminders = Reminders(
        store=Store(path),
        timer=FakeTimer(),
        announce=lambda job: None,
        fired=fired,
        clock=lambda: NOW,
    )
    return Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker()),
        reminders=reminders,
        clock=lambda: NOW,
    )


def rang(cmd, message="arriba", device="parlante"):
    cmd.reminders.fired.remember(OWNER, message, device, FIRED)


def test_without_a_duration_it_postpones_ten_minutes(cmd):
    rang(cmd)

    reply = cmd.postpone(OWNER, "")

    jobs = cmd.reminders.list(OWNER)
    assert [job.when for job in jobs] == [NOW + timedelta(minutes=10)]
    assert jobs[0].message == "arriba"
    assert "07:41" in reply
    assert "arriba" in reply


def test_a_duration_is_respected(cmd):
    rang(cmd)

    cmd.postpone(OWNER, "5m")

    assert cmd.reminders.list(OWNER)[0].when == NOW + timedelta(minutes=5)


def test_nothing_rang_means_nothing_to_postpone(cmd):
    reply = cmd.postpone(OWNER, "")

    assert cmd.reminders.list(OWNER) == []
    assert "nada que posponer" in reply


def test_a_bad_duration_explains_and_schedules_nothing(cmd):
    rang(cmd)

    reply = cmd.postpone(OWNER, "cuando pueda")

    assert cmd.reminders.list(OWNER) == []
    assert reply


def test_a_stranger_is_turned_away(cmd):
    rang(cmd)

    reply = cmd.postpone(STRANGER, "")

    assert "No estás en la lista" in reply
    assert cmd.reminders.list(OWNER) == []


def test_help_offers_it():
    assert "/posponer" in HELP


# --- botones ---------------------------------------------------------------


def test_a_button_runs_the_command_it_carries(cmd):
    rang(cmd)

    reply = cmd.press(OWNER, "posponer 10m")

    assert len(cmd.reminders.list(OWNER)) == 1
    assert "arriba" in reply


def test_a_button_only_runs_known_commands(cmd):
    reply = cmd.press(OWNER, "rm -rf")

    assert "No sé qué hacer" in reply


def test_a_button_from_a_stranger_is_turned_away(cmd):
    rang(cmd)

    reply = cmd.press(STRANGER, "posponer 10m")

    assert "No estás en la lista" in reply
    assert cmd.reminders.list(OWNER) == []

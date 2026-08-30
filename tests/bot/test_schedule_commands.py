import uuid
from datetime import datetime, timedelta

import pytest

from homeauto.bot.commands import Commands
from homeauto.config import Config
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import Store

UUID = uuid.UUID("d17e8311-d82e-5116-8f58-6292603bbc1b")
OWNER = 42
STRANGER = 99
NOW = datetime(2026, 8, 29, 21, 0)


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)


class FakeSpeaker:
    def say(self, text): pass
    def set_volume(self, percent): pass
    def stop(self): pass
    def device_name(self): return "Nest"


@pytest.fixture
def cmd(tmp_path):
    reminders = Reminders(store=Store(tmp_path / "jobs.db"), timer=FakeTimer(), announce=lambda job: None)
    config = Config(telegram_token="123:ABC", cast_uuid=UUID, allowed_chat_ids=frozenset({OWNER}))
    return Commands(config=config, speaker=FakeSpeaker(), reminders=reminders, clock=lambda: NOW)


def test_timer_schedules_and_confirms(cmd):
    reply = cmd.timer(OWNER, "10m sacá la pizza")

    jobs = cmd.reminders.list(OWNER)
    assert len(jobs) == 1
    assert jobs[0].when == NOW + timedelta(minutes=10)
    assert jobs[0].message == "sacá la pizza"
    assert jobs[0].repeat == "once"
    assert "21:10" in reply


def test_timer_rejects_what_it_cannot_parse(cmd):
    reply = cmd.timer(OWNER, "cuando salga el sol avisame")

    assert cmd.reminders.list(OWNER) == []
    assert "No entiendo" in reply


def test_timer_without_message_explains(cmd):
    reply = cmd.timer(OWNER, "10m")

    assert cmd.reminders.list(OWNER) == []
    assert "mensaje" in reply.lower()


def test_alarm_at_a_clock_time_rolls_to_tomorrow(cmd):
    cmd.alarm(OWNER, "7:30 arriba")

    job = cmd.reminders.list(OWNER)[0]
    assert job.when == datetime(2026, 8, 30, 7, 30)
    assert job.repeat == "once"


def test_daily_alarm_repeats(cmd):
    reply = cmd.alarm(OWNER, "diaria 7:30 arriba")

    job = cmd.reminders.list(OWNER)[0]
    assert job.repeat == "daily"
    assert job.when == datetime(2026, 8, 30, 7, 30)
    assert "todos los días" in reply.lower()


def test_list_says_when_there_is_nothing(cmd):
    assert "nada" in cmd.list(OWNER).lower()


def test_list_numbers_the_jobs(cmd):
    cmd.timer(OWNER, "10m pizza")
    cmd.alarm(OWNER, "7:30 arriba")

    reply = cmd.list(OWNER)

    assert "pizza" in reply
    assert "arriba" in reply
    for job in cmd.reminders.list(OWNER):
        assert str(job.id) in reply


def test_list_does_not_leak_other_chats(cmd):
    cmd.reminders.add(STRANGER, NOW + timedelta(hours=1), "secreto ajeno")

    assert "secreto" not in cmd.list(OWNER)


def test_cancel_removes_the_job(cmd):
    cmd.timer(OWNER, "10m pizza")
    job_id = cmd.reminders.list(OWNER)[0].id

    reply = cmd.cancel(OWNER, str(job_id))

    assert cmd.reminders.list(OWNER) == []
    assert "cancel" in reply.lower()


def test_cancel_needs_a_number(cmd):
    assert "número" in cmd.cancel(OWNER, "la pizza").lower()


def test_cancel_of_an_unknown_job_says_so(cmd):
    assert "no encontr" in cmd.cancel(OWNER, "4321").lower()


def test_stranger_cannot_schedule(cmd):
    reply = cmd.timer(STRANGER, "10m algo")

    assert cmd.reminders.list(STRANGER) == []
    assert "no est" in reply.lower()


def test_relative_time_shown_as_today(cmd):
    assert "hoy" in cmd.timer(OWNER, "10m pizza").lower()


def test_tomorrow_is_shown_as_tomorrow(cmd):
    assert "mañana" in cmd.alarm(OWNER, "7:30 arriba").lower()

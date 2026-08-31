from datetime import datetime, timedelta

import pytest

from homeauto.bot.commands import Commands
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import Store

from tests.conftest import FakeSpeaker, StubRegistry, make_config

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


@pytest.fixture
def cmd(tmp_path):
    reminders = Reminders(store=Store(tmp_path / "jobs.db"), timer=FakeTimer(), announce=lambda job: None)
    config = make_config(allowed={OWNER})
    return Commands(
        config=config,
        speakers=StubRegistry(parlante=FakeSpeaker()),
        reminders=reminders,
        clock=lambda: NOW,
    )


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


# --- alarmas por días de la semana -----------------------------------------


def test_weekday_alarm_fires_on_the_next_day_asked_for(cmd):
    reply = cmd.alarm(OWNER, "lun-vie 5:30 arriba")

    job = cmd.reminders.list(OWNER)[0]
    assert job.repeat == "weekly"
    assert job.weekdays == [1, 2, 3, 4, 5]
    assert job.when == datetime(2026, 8, 31, 5, 30)  # NOW es sábado: el lunes
    assert job.message == "arriba"
    assert "lun, mar, mié, jue, vie" in reply


def test_weekday_alarm_can_be_a_list_of_days(cmd):
    cmd.alarm(OWNER, "mar,jue 20:00 gimnasia")

    job = cmd.reminders.list(OWNER)[0]
    assert job.weekdays == [2, 4]
    assert job.when == datetime(2026, 9, 1, 20, 0)


def test_weekday_alarm_today_still_counts_if_the_hour_did_not_pass(cmd):
    cmd.alarm(OWNER, "sab 23:00 novela")  # NOW es sábado 21:00

    assert cmd.reminders.list(OWNER)[0].when == datetime(2026, 8, 29, 23, 0)


def test_weekday_alarm_accepts_the_target_device(cmd):
    cmd.alarm(OWNER, "en parlante lun-vie 5:30 arriba")

    job = cmd.reminders.list(OWNER)[0]
    assert job.devices == ["parlante"]
    assert job.weekdays == [1, 2, 3, 4, 5]


def test_weekday_alarm_needs_a_clock_time(cmd):
    reply = cmd.alarm(OWNER, "lun-vie 10m arriba")

    assert cmd.reminders.list(OWNER) == []
    assert "hora" in reply.lower()


def test_weekday_alarm_needs_a_message(cmd):
    reply = cmd.alarm(OWNER, "lun-vie 5:30")

    assert cmd.reminders.list(OWNER) == []
    assert "mensaje" in reply.lower()


def test_list_shows_which_days_a_weekly_alarm_uses(cmd):
    cmd.alarm(OWNER, "mar,jue 20:00 gimnasia")

    assert "mar, jue" in cmd.list(OWNER)

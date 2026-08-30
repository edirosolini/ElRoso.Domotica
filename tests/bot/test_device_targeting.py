from datetime import datetime, timedelta

import pytest

from homeauto.bot.commands import Commands
from homeauto.schedule.preferences import Preferences
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import Store

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
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
    parlante, tv = FakeSpeaker("parlante"), FakeSpeaker("tv")
    speakers = StubRegistry(parlante=parlante, tv=tv)
    reminders = Reminders(store=Store(tmp_path / "j.db"), timer=FakeTimer(), announce=lambda job: None)
    commands = Commands(
        config=make_config(allowed={OWNER}, devices={"parlante": None, "tv": None}),
        speakers=speakers,
        reminders=reminders,
        preferences=Preferences(tmp_path / "j.db"),
        clock=lambda: NOW,
    )
    return commands, parlante, tv


def test_without_a_target_it_uses_the_default(cmd):
    commands, parlante, tv = cmd

    commands.say(OWNER, "hola")

    assert parlante.said == ["hola"] and tv.said == []


def test_en_alias_picks_that_device(cmd):
    commands, parlante, tv = cmd

    reply = commands.say(OWNER, "en tv que bajen a comer")

    assert tv.said == ["que bajen a comer"]
    assert parlante.said == []
    assert "tv" in reply


def test_en_something_that_is_not_a_device_is_just_text(cmd):
    commands, parlante, tv = cmd

    commands.say(OWNER, "en casa hace frío")

    assert parlante.said == ["en casa hace frío"], "no comerse palabras del mensaje"
    assert tv.said == []


def test_usar_changes_the_default_for_next_time(cmd):
    commands, parlante, tv = cmd

    commands.use(OWNER, "tv")
    commands.say(OWNER, "hola")

    assert tv.said == ["hola"] and parlante.said == []


def test_usar_survives_and_can_be_changed_back(cmd):
    commands, parlante, tv = cmd

    commands.use(OWNER, "tv")
    commands.use(OWNER, "parlante")
    commands.say(OWNER, "hola")

    assert parlante.said == ["hola"]


def test_usar_an_unknown_device_lists_what_there_is(cmd):
    commands, _, _ = cmd

    reply = commands.use(OWNER, "cocina")

    assert "cocina" in reply
    assert "parlante" in reply and "tv" in reply


def test_devices_command_lists_them_and_marks_the_active_one(cmd):
    commands, _, _ = cmd

    reply = commands.devices(OWNER)

    assert "parlante" in reply and "tv" in reply
    assert "◀" in reply or "activo" in reply.lower()


def test_volume_and_stop_also_respect_the_target(cmd):
    commands, parlante, tv = cmd

    commands.use(OWNER, "tv")
    commands.volume(OWNER, "30")
    commands.stop(OWNER)

    assert tv.volumes == [30] and tv.stopped == 1
    assert parlante.volumes == [] and parlante.stopped == 0


def test_a_timer_remembers_which_device_it_was_for(cmd):
    commands, _, _ = cmd

    commands.timer(OWNER, "en tv 10m que bajen")

    job = commands.reminders.list(OWNER)[0]
    assert job.device == "tv"
    assert job.message == "que bajen"
    assert job.when == NOW + timedelta(minutes=10)


def test_a_timer_without_a_target_records_the_current_default(cmd):
    commands, _, _ = cmd

    commands.use(OWNER, "tv")
    commands.timer(OWNER, "10m algo")

    assert commands.reminders.list(OWNER)[0].device == "tv"


def test_alarm_also_takes_a_target(cmd):
    commands, _, _ = cmd

    commands.alarm(OWNER, "en tv diaria 7:30 arriba")

    job = commands.reminders.list(OWNER)[0]
    assert job.device == "tv"
    assert job.repeat == "daily"


def test_the_list_shows_the_device(cmd):
    commands, _, _ = cmd

    commands.timer(OWNER, "en tv 10m que bajen")

    assert "tv" in commands.list(OWNER)

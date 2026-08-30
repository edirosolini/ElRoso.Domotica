from datetime import datetime

import pytest

from homeauto.bot.commands import Commands
from homeauto.schedule.preferences import Preferences
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import Store
from homeauto.voice.caster import CastError

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


def build(tmp_path, **failures):
    speakers = {
        alias: FakeSpeaker(alias, failures.get(alias))
        for alias in ("parlante", "comedor", "recamara")
    }
    registry = StubRegistry(**speakers)
    reminders = Reminders(store=Store(tmp_path / "j.db"), timer=FakeTimer(), announce=lambda job: None)
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=registry,
        reminders=reminders,
        preferences=Preferences(tmp_path / "j.db"),
        clock=lambda: NOW,
    )
    return commands, speakers


def test_two_devices_separated_by_comma(tmp_path):
    cmd, spk = build(tmp_path)

    reply = cmd.say(OWNER, "en comedor,recamara que bajen")

    assert spk["comedor"].said == ["que bajen"]
    assert spk["recamara"].said == ["que bajen"]
    assert spk["parlante"].said == []
    assert "comedor" in reply and "recamara" in reply


def test_spaces_after_the_comma_are_fine(tmp_path):
    cmd, spk = build(tmp_path)

    cmd.say(OWNER, "en comedor, recamara que bajen")

    assert spk["comedor"].said == ["que bajen"]
    assert spk["recamara"].said == ["que bajen"]


def test_todos_reaches_every_device(tmp_path):
    cmd, spk = build(tmp_path)

    cmd.say(OWNER, "en todos la cena está lista")

    for alias, speaker in spk.items():
        assert speaker.said == ["la cena está lista"], f"{alias} se quedó sin el aviso"


def test_a_repeated_device_is_only_told_once(tmp_path):
    cmd, spk = build(tmp_path)

    cmd.say(OWNER, "en comedor,comedor hola")

    assert spk["comedor"].said == ["hola"]


def test_an_unknown_device_in_the_list_is_an_error(tmp_path):
    cmd, spk = build(tmp_path)

    reply = cmd.say(OWNER, "en comedor,cocina hola")

    assert "cocina" in reply
    assert spk["comedor"].said == [], "o van todos o no va ninguno"


def test_a_single_unknown_word_is_still_just_text(tmp_path):
    cmd, spk = build(tmp_path)

    cmd.say(OWNER, "en casa hace frío")

    assert spk["parlante"].said == ["en casa hace frío"]


def test_one_broken_device_does_not_silence_the_others(tmp_path):
    cmd, spk = build(tmp_path, recamara=CastError("apagado"))

    reply = cmd.say(OWNER, "en todos atención")

    assert spk["parlante"].said == ["atención"]
    assert spk["comedor"].said == ["atención"]
    assert "recamara" in reply and "apagado" in reply


def test_when_every_device_fails_it_says_so(tmp_path):
    cmd, _ = build(
        tmp_path,
        parlante=CastError("apagado"),
        comedor=CastError("apagado"),
        recamara=CastError("apagado"),
    )

    reply = cmd.say(OWNER, "en todos hola")

    assert "no pude" in reply.lower()


def test_volume_applies_to_several(tmp_path):
    cmd, spk = build(tmp_path)

    cmd.volume(OWNER, "en comedor,recamara 30")

    assert spk["comedor"].volumes == [30]
    assert spk["recamara"].volumes == [30]
    assert spk["parlante"].volumes == []


def test_stop_applies_to_several(tmp_path):
    cmd, spk = build(tmp_path)

    cmd.stop(OWNER, "en todos")

    assert all(s.stopped == 1 for s in spk.values())


def test_a_timer_remembers_all_its_devices(tmp_path):
    cmd, _ = build(tmp_path)

    cmd.timer(OWNER, "en comedor,recamara 10m que bajen")

    job = cmd.reminders.list(OWNER)[0]
    assert job.devices == ["comedor", "recamara"]


def test_the_list_shows_every_device_of_a_job(tmp_path):
    cmd, _ = build(tmp_path)

    cmd.timer(OWNER, "en comedor,recamara 10m que bajen")
    reply = cmd.list(OWNER)

    assert "comedor" in reply and "recamara" in reply


def test_usar_accepts_several_as_the_default(tmp_path):
    cmd, spk = build(tmp_path)

    cmd.use(OWNER, "comedor,recamara")
    cmd.say(OWNER, "hola")

    assert spk["comedor"].said == ["hola"]
    assert spk["recamara"].said == ["hola"]
    assert spk["parlante"].said == []

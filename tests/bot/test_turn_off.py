from datetime import datetime

from homeauto.bot.commands import Commands
from homeauto.schedule.preferences import Preferences
from homeauto.voice.caster import CastError

from tests.conftest import StubRegistry, make_config

OWNER = 42
NOW = datetime(2026, 8, 29, 21, 0)


class FakeSpeakerOff:
    def __init__(self, name, fail=None):
        self.name = name
        self.turned_off = 0
        self.fail = fail

    def turn_off(self):
        if self.fail:
            raise self.fail
        self.turned_off += 1


def build(tmp_path, **failures):
    speakers = {
        alias: FakeSpeakerOff(alias, failures.get(alias))
        for alias in ("parlante", "comedor", "recamara")
    }
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        preferences=Preferences(tmp_path / "p.db"),
        clock=lambda: NOW,
    )
    return commands, speakers


def test_turns_off_the_default_device(tmp_path):
    cmd, spk = build(tmp_path)

    cmd.turn_off(OWNER, "")

    assert spk["parlante"].turned_off == 1
    assert spk["comedor"].turned_off == 0


def test_turns_off_a_named_device(tmp_path):
    cmd, spk = build(tmp_path)

    reply = cmd.turn_off(OWNER, "en comedor")

    assert spk["comedor"].turned_off == 1
    assert "comedor" in reply


def test_turns_off_everything(tmp_path):
    cmd, spk = build(tmp_path)

    cmd.turn_off(OWNER, "en todos")

    assert all(s.turned_off == 1 for s in spk.values())


def test_a_device_that_fails_does_not_stop_the_rest(tmp_path):
    cmd, spk = build(tmp_path, recamara=CastError("no responde"))

    reply = cmd.turn_off(OWNER, "en todos")

    assert spk["parlante"].turned_off == 1
    assert spk["comedor"].turned_off == 1
    assert "recamara" in reply and "no responde" in reply


def test_a_stranger_cannot_turn_off_the_house(tmp_path):
    cmd, spk = build(tmp_path)

    cmd.turn_off(99, "en todos")

    assert all(s.turned_off == 0 for s in spk.values())

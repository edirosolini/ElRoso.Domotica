"""Los equipos se escriben y se muestran con su nombre en castellano; por dentro, el alias."""

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
    def schedule(self, key, when, action):
        pass

    def unschedule(self, key):
        pass


def build(tmp_path, **failures):
    speakers = {
        alias: FakeSpeaker(alias, failures.get(alias))
        for alias in ("comedor", "recamara", "habitacion")
    }
    preferences = Preferences(tmp_path / "j.db")
    store = Store(tmp_path / "j.db")
    reminders = Reminders(store=store, timer=FakeTimer(), announce=lambda job: None)
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        reminders=reminders,
        preferences=preferences,
        clock=lambda: NOW,
    )
    return commands, speakers, preferences, store


@pytest.mark.parametrize("written", ["Recámara", "RECAMARA", "recámara"])
def test_use_takes_the_name_however_it_was_written(tmp_path, written):
    cmd, _, preferences, _ = build(tmp_path)

    cmd.use(OWNER, written)

    assert preferences.default_device(OWNER) == "recamara"


def test_say_in_the_spanish_name_only_says_the_message_there(tmp_path):
    cmd, spk, _, _ = build(tmp_path)

    cmd.say(OWNER, "en Recámara hola")

    assert spk["recamara"].said == ["hola"]
    assert spk["comedor"].said == []


def test_a_list_of_spanish_names_reaches_each_one(tmp_path):
    cmd, spk, _, _ = build(tmp_path)

    cmd.say(OWNER, "en Recámara, Habitación hola")

    assert spk["recamara"].said == ["hola"]
    assert spk["habitacion"].said == ["hola"]


def test_devices_lists_the_spanish_names_and_marks_the_active_one(tmp_path):
    cmd, _, _, _ = build(tmp_path)
    cmd.use(OWNER, "recamara")

    reply = cmd.devices(OWNER)

    assert reply.startswith("Parlantes y teles:\n")
    assert "Recámara  ◀ activo" in reply
    assert "Habitación" in reply
    assert "Comedor" in reply


def test_use_answers_with_the_name(tmp_path):
    cmd, _, _, _ = build(tmp_path)

    assert cmd.use(OWNER, "recamara,habitacion") == "Listo, ahora uso Recámara, Habitación"


def test_an_unknown_device_lists_the_names(tmp_path):
    cmd, _, _, _ = build(tmp_path)

    reply = cmd.use(OWNER, "garage")

    assert reply == "No conozco 'garage'. Tengo: Comedor, Recámara, Habitación"


def test_an_unknown_one_in_a_list_lists_the_names(tmp_path):
    cmd, _, _, _ = build(tmp_path)

    reply = cmd.say(OWNER, "en recamara,garage hola")

    assert reply == "No conozco: garage. Tengo: Comedor, Recámara, Habitación"


def test_said_and_failed_name_the_devices(tmp_path):
    cmd, _, _, _ = build(tmp_path, habitacion=CastError("no responde"))

    reply = cmd.say(OWNER, "en recamara,habitacion hola")

    assert "en Recámara" in reply
    assert "No pude en:\nHabitación: no responde" in reply


def test_timer_answers_with_the_name_and_stores_the_alias(tmp_path):
    cmd, _, _, store = build(tmp_path)

    reply = cmd.timer(OWNER, "en Recámara 10m sacá la pizza")

    assert " en Recámara " in reply
    assert [job.device for job in store.pending(OWNER)] == ["recamara"]


def test_alarm_answers_with_the_name(tmp_path):
    cmd, _, _, _ = build(tmp_path)

    reply = cmd.alarm(OWNER, "en habitacion diaria 7:30 arriba")

    assert " en Habitación " in reply


def test_list_shows_the_name(tmp_path):
    cmd, _, _, _ = build(tmp_path)
    cmd.timer(OWNER, "en recamara 10m sacá la pizza")

    assert "· Recámara" in cmd.list(OWNER)

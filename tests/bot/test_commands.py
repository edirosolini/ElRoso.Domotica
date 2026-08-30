import pytest

from homeauto.bot.commands import Commands
from homeauto.voice.caster import CastError
from homeauto.voice.tts import TtsError

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
STRANGER = 99


def build(allowed=(OWNER,), speaker=None):
    speaker = speaker or FakeSpeaker()
    commands = Commands(config=make_config(allowed), speakers=StubRegistry(parlante=speaker))
    return commands, speaker


def test_say_speaks_the_text():
    cmd, speaker = build()

    reply = cmd.say(OWNER, "buenas noches")

    assert speaker.said == ["buenas noches"]
    assert "buenas noches" in reply


def test_say_without_text_asks_for_it():
    cmd, speaker = build()

    reply = cmd.say(OWNER, "   ")

    assert speaker.said == []
    assert "qué" in reply.lower()


def test_stranger_is_refused_and_the_speaker_is_not_touched():
    cmd, speaker = build()

    reply = cmd.say(STRANGER, "hola")

    assert speaker.said == []
    assert "no est" in reply.lower()


def test_open_enrollment_lets_anyone_in_and_shows_the_chat_id():
    cmd, speaker = build(allowed=())

    reply = cmd.say(STRANGER, "hola")

    assert speaker.said == ["hola"]
    assert str(STRANGER) in reply, "tiene que mostrar el chat id para poder cerrarlo"


def test_volume_is_set():
    cmd, speaker = build()

    reply = cmd.volume(OWNER, "40")

    assert speaker.volumes == [40]
    assert "40" in reply


def test_volume_needs_a_number():
    cmd, speaker = build()

    reply = cmd.volume(OWNER, "fuerte")

    assert speaker.volumes == []
    assert "número" in reply.lower()


def test_volume_out_of_range_surfaces_the_reason():
    cmd, _ = build(speaker=FakeSpeaker(fail=CastError("El volumen tiene que estar entre 0 y 100")))

    reply = cmd.volume(OWNER, "500")

    assert "entre 0 y 100" in reply


def test_cast_failure_is_reported_without_a_traceback():
    cmd, _ = build(speaker=FakeSpeaker(fail=CastError("No encontré el dispositivo")))

    reply = cmd.say(OWNER, "hola")

    assert "No encontré el dispositivo" in reply
    assert "Traceback" not in reply


def test_tts_failure_is_reported():
    cmd, _ = build(speaker=FakeSpeaker(fail=TtsError("piper falló")))

    reply = cmd.say(OWNER, "hola")

    assert "piper falló" in reply


def test_stop_stops():
    cmd, speaker = build()

    reply = cmd.stop(OWNER)

    assert speaker.stopped == 1
    assert reply


def test_where_lists_the_devices():
    cmd, _ = build()

    assert "parlante" in cmd.where(OWNER)


def test_start_greets_and_lists_the_commands():
    cmd, _ = build()

    reply = cmd.start(OWNER)

    assert "/decir" in reply
    assert "/volumen" in reply

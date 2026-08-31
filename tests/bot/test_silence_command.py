"""/silencio: callar la casa un rato, sin tocar el horario de descanso."""

from datetime import datetime

import pytest

from homeauto.bot.commands import Commands
from homeauto.quiet import Hush, HushStore, QuietHours

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
STRANGER = 99
NOON = datetime(2026, 8, 31, 12, 0)


@pytest.fixture
def cmd(tmp_path):
    hush = Hush(
        hours=QuietHours.parse("23:00", "07:00"),
        store=HushStore(tmp_path / "jobs.db"),
        clock=lambda: NOON,
    )
    return Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker()),
        quiet=hush,
        clock=lambda: NOON,
    )


def test_asking_for_silence_says_until_when(cmd):
    reply = cmd.silence(OWNER, "2h")

    assert "14:00" in reply
    assert cmd.quiet.is_quiet(NOON) is True


def test_the_speaker_stays_quiet_during_the_silence(cmd):
    cmd.silence(OWNER, "30m")

    reply = cmd.say(OWNER, "hola")

    assert cmd.speakers.get("parlante").said == []
    assert "no lo dije en voz alta" in reply


def test_without_a_duration_it_reports_what_is_going_on(cmd):
    assert "descanso" in cmd.silence(OWNER, "").lower()

    cmd.silence(OWNER, "2h")

    assert "14:00" in cmd.silence(OWNER, "")


def test_a_duration_it_cannot_read_is_explained(cmd):
    reply = cmd.silence(OWNER, "un rato largo")

    assert cmd.quiet.is_quiet(NOON) is False
    assert "no entiendo" in reply.lower()


def test_speaking_again_cuts_the_silence_short(cmd):
    cmd.silence(OWNER, "2h")

    reply = cmd.speak(OWNER, "")

    assert cmd.quiet.is_quiet(NOON) is False
    assert "vuelvo a hablar" in reply.lower()


def test_speaking_when_nobody_asked_for_silence(cmd):
    assert "no estaba" in cmd.speak(OWNER, "").lower()


def test_a_stranger_cannot_silence_the_house(cmd):
    reply = cmd.silence(STRANGER, "2h")

    assert cmd.quiet.is_quiet(NOON) is False
    assert "no est" in reply.lower()


def test_without_the_ad_hoc_silence_it_says_so():
    """Con unas QuietHours sueltas no hay nada que mover."""
    plain = Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker()),
        quiet=QuietHours.parse("23:00", "07:00"),
        clock=lambda: NOON,
    )

    assert "no tengo" in plain.silence(OWNER, "2h").lower()
    assert "no tengo" in plain.speak(OWNER, "").lower()

"""/silencio: callar la casa un rato, sin tocar el horario de descanso."""

from datetime import datetime

import pytest

from homeauto.bot.commands import Commands, with_actions
from homeauto.quiet import AwayStore, Hush, HushStore, QuietHours

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
        away=AwayStore(tmp_path / "jobs.db"),
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


def test_asking_for_silence_offers_to_talk_again(cmd):
    reply = with_actions(cmd.silence, OWNER, "2h")

    assert reply.text == "Listo, no hablo hasta las 14:00."
    assert reply.actions == (("Volver a hablar", "hablar"),)


def test_the_silence_status_offers_to_talk_again(cmd):
    cmd.silence(OWNER, "2h")

    reply = with_actions(cmd.silence, OWNER, "")

    assert reply.text == "En silencio hasta las 14:00."
    assert reply.actions[0] == ("Volver a hablar", "hablar")


SILENCE_TOPIC = [
    ("Silencio una hora", "silencio 1h"),
    ("Volver a hablar", "hablar"),
    ("Vacaciones", "vacaciones"),
    ("⬅ Temas", "inicio"),
]


def test_an_empty_silence_adds_the_buttons_of_its_topic(cmd):
    reply = with_actions(cmd.silence, OWNER, "")

    assert reply.text.startswith("Estoy hablando.")
    assert list(reply.actions) == SILENCE_TOPIC


def test_an_empty_silence_does_not_repeat_a_button(cmd):
    cmd.silence(OWNER, "2h")

    reply = with_actions(cmd.silence, OWNER, "")

    assert reply.actions == (
        ("Volver a hablar", "hablar"),
        ("Silencio una hora", "silencio 1h"),
        ("Vacaciones", "vacaciones"),
        ("⬅ Temas", "inicio"),
    )


def test_an_empty_silence_on_vacation_keeps_the_way_back(cmd):
    cmd.quiet.start_away(datetime(2026, 9, 10))

    reply = with_actions(cmd.silence, OWNER, "")

    assert reply.actions[0] == ("Volví de vacaciones", "vacaciones off")
    assert ("Silencio una hora", "silencio 1h") in reply.actions


def test_a_silence_with_a_duration_does_not_add_the_topic(cmd):
    reply = with_actions(cmd.silence, OWNER, "1h")

    assert ("⬅ Temas", "inicio") not in reply.actions


def test_an_empty_silence_from_the_control_screen_adds_the_topic_too(cmd):
    reply = with_actions(cmd.press, OWNER, "silencio")

    assert list(reply.actions) == SILENCE_TOPIC


def test_a_stranger_gets_no_topic_buttons(cmd):
    assert with_actions(cmd.silence, STRANGER, "").actions == ()


def test_the_speaker_stays_quiet_during_the_silence(cmd):
    cmd.silence(OWNER, "30m")

    reply = cmd.say(OWNER, "hola")

    assert cmd.speakers.get("parlante").said == []
    assert "no lo dije en voz alta" in reply


def test_without_a_duration_it_reports_what_is_going_on(cmd):
    assert "descanso" in cmd.silence(OWNER, "").lower()

    cmd.silence(OWNER, "2h")

    assert "14:00" in cmd.silence(OWNER, "")


def test_a_garbled_duration_keeps_the_duration_hint(cmd):
    reply = cmd.silence(OWNER, "2x")

    assert reply == "No entendí cuánto tiempo. Probá así: 10m o 1h30m"


def test_a_duration_it_cannot_read_is_explained(cmd):
    reply = cmd.silence(OWNER, "un rato largo")

    assert cmd.quiet.is_quiet(NOON) is False
    assert reply == "No entendí cuánto tiempo. Probá así: 10m o 1h30m"


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

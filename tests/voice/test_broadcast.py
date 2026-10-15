"""La voz de la casa: a qué equipos, con qué volumen y qué queda escrito."""

from datetime import datetime

import pytest

from homeauto.quiet import QuietHours
from homeauto.voice.broadcast import HouseVoice

from tests.conftest import FakeSpeaker, StubRegistry

NOON = datetime(2026, 8, 31, 12, 0)
NIGHT = datetime(2026, 8, 31, 23, 30)


def build(clock=lambda: NOON, quiet=None):
    speaker = FakeSpeaker("parlante")
    written = []
    house = HouseVoice(
        speakers=StubRegistry(parlante=speaker),
        default_devices=["parlante"],
        notify=lambda chat_id, text: written.append(text),
        chat_ids=[42],
        quiet=quiet,
        clock=clock,
    )
    return house, speaker, written


def test_the_chat_copy_can_say_more_than_the_speaker():
    house, speaker, written = build(clock=lambda: NIGHT, quiet=QuietHours.parse("23:00", "07:00"))

    house.announce("vpn-vps no responde", written="vpn-vps no responde\nHTTP 503 en 1.24s")

    assert speaker.said == [], "en descanso no se habla"
    assert "HTTP 503" in written[0], "el detalle sirve leído"


def test_what_is_spoken_never_carries_the_written_detail():
    house, speaker, _ = build()

    house.announce("vpn-vps no responde", written="vpn-vps no responde\nHTTP 503 en 1.24s")

    assert speaker.said == ["vpn-vps no responde"]


def test_an_urgent_announcement_sounds_before_it_speaks():
    house, speaker, _ = build()

    house.announce("producción caída", urgent=True)
    house.announce("veinte grados")

    assert speaker.chimes == [True, False]


def test_an_urgent_announcement_keeps_the_alarm_beeps_and_the_usual_floor():
    from homeauto.voice import chime

    house, speaker, _ = build()

    house.announce("producción caída", urgent=True)

    assert chime.sound(speaker.chimes[0]) == chime.ALARM
    assert speaker.min_volumes == [None], "None es el piso propio del equipo, sesenta"


# --- botones -----------------------------------------------------------------

ACTIONS = (("Ver estado", "estado"),)


def build_with_buttons(clock=lambda: NOON, quiet=None):
    sent = []
    house = HouseVoice(
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        default_devices=["parlante"],
        notify=lambda chat_id, text, actions=(): sent.append((text, actions)),
        chat_ids=[42],
        quiet=quiet,
        clock=clock,
    )
    return house, sent


def test_telling_everyone_can_carry_buttons():
    house, sent = build_with_buttons()

    house.tell_everyone("⚠️ vps no responde", actions=ACTIONS)

    assert sent == [("⚠️ vps no responde", ACTIONS)]


def test_a_resting_announcement_keeps_its_buttons():
    house, sent = build_with_buttons(clock=lambda: NIGHT, quiet=QuietHours.parse("23:00", "07:00"))

    house.announce("vps no responde", actions=ACTIONS)

    assert sent[0][1] == ACTIONS


def test_without_buttons_the_notifier_gets_two_arguments():
    """La API y los tests viejos usan un notificador de dos argumentos."""
    house, _, written = build(clock=lambda: NIGHT, quiet=QuietHours.parse("23:00", "07:00"))

    house.announce("veinte grados")
    house.tell_everyone("hola")

    assert len(written) == 2


# --- solo por el parlante --------------------------------------------------------


def test_speak_only_says_it_and_writes_nothing():
    from homeauto.voice import chime

    house, speaker, written = build()

    assert house.speak_only("Se cortó internet.", chime=chime.SOFT) is True

    assert speaker.said == ["Se cortó internet."]
    assert speaker.chimes == [chime.SOFT]
    assert written == [], "no se escribe al chat"


def test_speak_only_keeps_quiet_while_resting():
    house, speaker, written = build(clock=lambda: NIGHT, quiet=QuietHours.parse("23:00", "07:00"))

    assert house.speak_only("Se cortó internet.") is False

    assert speaker.said == []
    assert written == [], "en descanso tampoco se escribe"


def test_speak_only_keeps_quiet_under_a_hush(tmp_path):
    from datetime import timedelta

    from homeauto.quiet import Hush, HushStore

    hush = Hush(
        hours=QuietHours.parse("23:00", "07:00"),
        store=HushStore(tmp_path / "jobs.db"),
        clock=lambda: NOON,
    )
    hush.start(timedelta(hours=1))
    house, speaker, written = build(quiet=hush)

    assert house.speak_only("Se cortó internet.") is False

    assert speaker.said == [] and written == []


def test_speak_only_survives_a_broken_speaker():
    house, speaker, written = build()

    def broken(text, chime=False, min_volume=None):
        raise RuntimeError("apagado")

    speaker.say = broken

    assert house.speak_only("Se cortó internet.") is False
    assert written == []


# --- modo vacaciones ---------------------------------------------------------


def away_hush(tmp_path, now=NOON):
    from homeauto.quiet import AwayStore, Hush, HushStore

    path = tmp_path / "jobs.db"
    hush = Hush(
        hours=QuietHours.parse("23:00", "07:00"),
        store=HushStore(path),
        clock=lambda: now,
        away=AwayStore(path),
    )
    hush.start_away(datetime(2026, 9, 25, 0, 0))
    return hush


def test_without_vacations_the_urgent_still_wakes_the_house_at_night():
    house, speaker, written = build(clock=lambda: NIGHT, quiet=QuietHours.parse("23:00", "07:00"))

    result = house.announce("producción caída", urgent=True)

    assert speaker.said == ["producción caída"]
    assert result["spoken"] is True and written == []


def test_on_vacation_even_the_urgent_is_only_written(tmp_path):
    house, sent = build_with_buttons(quiet=away_hush(tmp_path))
    speaker = house.speakers.get("parlante")

    result = house.announce("producción caída", urgent=True, actions=ACTIONS)

    assert speaker.said == []
    assert result["spoken"] is False and result["notified"] is True
    [(text, actions)] = sent
    assert "producción caída" in text
    assert "De vacaciones hasta el 25/09" in text
    assert actions == ACTIONS


def test_on_vacation_the_everyday_notices_are_only_written(tmp_path):
    house, speaker, written = build(quiet=away_hush(tmp_path))

    result = house.announce("Hoy llueve a la tarde.")

    assert speaker.said == []
    assert result["notified"] is True
    assert "Hoy llueve" in written[0]


def test_on_vacation_speak_only_keeps_quiet(tmp_path):
    house, speaker, written = build(quiet=away_hush(tmp_path))

    assert house.speak_only("Se cortó internet.") is False
    assert speaker.said == [] and written == []

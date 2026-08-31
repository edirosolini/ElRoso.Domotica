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

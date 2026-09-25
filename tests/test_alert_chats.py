"""Los avisos de vigilancia van solo a los chats de alertas; el resto, a todos."""

from datetime import datetime

import pytest

from homeauto import main
from homeauto.briefing import Briefing
from homeauto.closing import Closing
from homeauto.config import Config, ConfigError
from homeauto.quiet import QuietHours
from homeauto.voice.broadcast import HouseVoice
from homeauto.watch.seq import SeqEvent
from homeauto.watch.status import Status

from tests.conftest import FakeSpeaker, StubRegistry

VALID_UUID = "d17e8311-d82e-5116-8f58-6292603bbc1b"
NOON = datetime(2026, 9, 25, 12, 0)
NIGHT = datetime(2026, 9, 25, 23, 30)
OWNER = 42
OTHER = 77


# --- config ------------------------------------------------------------------

def load(tmp_path, body):
    path = tmp_path / "domotica.env"
    path.write_text(f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\n{body}", encoding="utf-8")
    return Config.from_file(path)


def test_without_alert_chats_the_alerts_go_to_everyone(tmp_path):
    cfg = load(tmp_path, "ALLOWED_CHAT_IDS=42,77\n")

    assert cfg.alert_recipients == {OWNER, OTHER}


def test_alert_chats_narrow_who_gets_the_alerts(tmp_path):
    cfg = load(tmp_path, "ALLOWED_CHAT_IDS=42,77\nALERT_CHAT_IDS=42\n")

    assert cfg.alert_recipients == {OWNER}


def test_an_alert_chat_outside_the_allowed_list_fails_the_start(tmp_path):
    """Sus botones serían rechazados: el aviso llegaría y no se podría usar."""
    with pytest.raises(ConfigError, match="ALERT_CHAT_IDS"):
        load(tmp_path, "ALLOWED_CHAT_IDS=42\nALERT_CHAT_IDS=99\n")


def test_an_alert_chat_that_is_not_a_number_fails_the_start(tmp_path):
    with pytest.raises(ConfigError, match="ALERT_CHAT_IDS"):
        load(tmp_path, "ALLOWED_CHAT_IDS=42\nALERT_CHAT_IDS=yo\n")


# --- HouseVoice ----------------------------------------------------------------

def build_house(clock=lambda: NOON, quiet=None, alert_chat_ids=(OWNER,)):
    speaker = FakeSpeaker("parlante")
    sent = []
    house = HouseVoice(
        speakers=StubRegistry(parlante=speaker),
        default_devices=["parlante"],
        notify=lambda chat_id, text, actions=(): sent.append((chat_id, text)),
        chat_ids=[OWNER, OTHER],
        quiet=quiet,
        clock=clock,
        alert_chat_ids=alert_chat_ids,
    )
    return house, speaker, sent


def test_telling_everyone_still_reaches_everyone():
    house, _, sent = build_house()

    house.tell_everyone("va a llover")

    assert sorted(chat for chat, _ in sent) == [OWNER, OTHER]


def test_an_alert_only_reaches_the_alert_chats():
    house, _, sent = build_house()

    house.tell("⚠️ vps no responde", others=None)

    assert sent == [(OWNER, "⚠️ vps no responde")]


def test_the_others_can_get_their_own_copy():
    house, _, sent = build_house()

    house.tell("completo", others="sin servicios")

    assert dict(sent) == {OWNER: "completo", OTHER: "sin servicios"}


def test_an_empty_copy_for_the_others_is_not_sent():
    house, _, sent = build_house()

    house.tell("vps caído", others="")

    assert sent == [(OWNER, "vps caído")]


def test_without_alert_chats_everyone_gets_the_alerts():
    house, _, sent = build_house(alert_chat_ids=())

    house.tell("⚠️ vps no responde", others=None)

    assert sorted(chat for chat, _ in sent) == [OWNER, OTHER]


def test_a_resting_alert_only_reaches_the_alert_chats():
    house, speaker, sent = build_house(
        clock=lambda: NIGHT, quiet=QuietHours.parse("23:00", "07:00")
    )

    house.announce("vps no responde", others=None)

    assert speaker.said == []
    assert [chat for chat, _ in sent] == [OWNER]


def test_a_resting_announcement_gives_the_others_their_copy():
    house, _, sent = build_house(clock=lambda: NIGHT, quiet=QuietHours.parse("23:00", "07:00"))

    house.announce("dicho", written="completo", others="sin servicios")

    copies = dict(sent)
    assert "completo" in copies[OWNER]
    assert "sin servicios" in copies[OTHER]
    assert "descanso" in copies[OTHER]


def test_the_speaker_does_not_care_about_the_audience():
    house, speaker, _ = build_house()

    house.announce("vps no responde", others=None)

    assert speaker.said == ["vps no responde"]


# --- el cableado de los avisos ---------------------------------------------------

class FakeHouse:
    def __init__(self, spoken=True):
        self.spoken = spoken
        self.announced = []
        self.told = []

    def announce(self, text, urgent=False, written=None, actions=(), others=main.SAME):
        self.announced.append(others)
        return {"spoken": self.spoken}

    def tell(self, text, others=main.SAME, actions=()):
        self.told.append((text, others))


def test_a_monitor_or_seq_alert_is_written_only_to_the_alert_chats():
    house = FakeHouse(spoken=True)

    main._alert(house, "vps no responde", True)

    assert house.told == [("🚨 vps no responde", None)]


def test_an_unspoken_alert_tells_the_house_it_is_only_for_the_alert_chats():
    house = FakeHouse(spoken=False)

    main._alert(house, "vps no responde", False)

    assert house.announced == [None]


def test_an_announcement_can_carry_a_copy_for_the_others():
    house = FakeHouse(spoken=True)

    main._announce(house, "dicho", "completo", others="sin servicios")

    assert house.told == [("🔔 completo", "🔔 sin servicios")]


def test_an_announcement_without_a_copy_for_the_others_is_the_same_for_all():
    house = FakeHouse(spoken=True)

    main._announce(house, "va a llover")

    assert house.told == [("🔔 va a llover", main.SAME)]


def test_an_empty_copy_for_the_others_stays_empty():
    house = FakeHouse(spoken=True)

    main._announce(house, "vps caído", others="")

    assert house.told == [("🔔 vps caído", "")]


# --- resumen y cierre --------------------------------------------------------------

class FakeMonitor:
    def __init__(self, **up_by_name):
        self.state = up_by_name

    def snapshot(self):
        return {name: Status(name, up, 0, not up, "detalle", NOON) for name, up in self.state.items()}


class FakeWeather:
    def spoken(self):
        return "Hay sol."

    def spoken_tomorrow(self):
        return "Mañana hay sol."


class FakeNight:
    def errors_since(self, since):
        return [SeqEvent(datetime(2026, 9, 25, 3, 0), "Error", "explotó", "Facturador", "Production")]


def test_the_briefing_for_the_others_leaves_out_the_services_and_seq():
    summary = Briefing(weather=FakeWeather(), monitor=FakeMonitor(vps=False), seq=FakeNight()).speech()

    assert "vps" in summary.written
    assert "Facturador" in summary.written
    assert "Hay sol." in summary.public
    assert "vps" not in summary.public
    assert "Facturador" not in summary.public
    assert "explotó" not in summary.public


def test_the_briefing_for_the_others_is_the_same_on_a_calm_day():
    summary = Briefing(weather=FakeWeather(), monitor=FakeMonitor(vps=True)).speech()

    assert summary.public == summary.written


def test_the_briefing_for_the_others_is_never_empty():
    summary = Briefing(monitor=FakeMonitor(vps=False)).speech()

    assert summary.public
    assert "vps" not in summary.public


def test_the_closing_for_the_others_leaves_out_the_services():
    summary = Closing(weather=FakeWeather(), monitor=FakeMonitor(vps=False)).speech()

    assert "vps" in summary.spoken
    assert summary.written == summary.spoken
    assert "Mañana hay sol." in summary.public
    assert "vps" not in summary.public


def test_a_closing_with_only_services_down_says_nothing_to_the_others():
    summary = Closing(monitor=FakeMonitor(vps=False)).speech()

    assert summary.spoken
    assert summary.public == ""


def test_the_closing_text_is_still_what_is_spoken():
    closing = Closing(weather=FakeWeather(), monitor=FakeMonitor(vps=False))

    assert closing.text() == closing.speech().spoken

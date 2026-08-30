from datetime import datetime, time

import pytest

from homeauto.api import ApiError, ApiService, Unauthorized
from homeauto.quiet import QuietHours

from tests.conftest import FakeSpeaker, StubRegistry

TOKEN = "secreto-largo-de-verdad"
NIGHT = QuietHours(start=time(23, 0), end=time(7, 0))
AT_NIGHT = datetime(2026, 8, 30, 3, 0)
BY_DAY = datetime(2026, 8, 30, 15, 0)


def build(now=BY_DAY, chats=(42,)):
    speakers = {alias: FakeSpeaker(alias) for alias in ("parlante", "comedor")}
    sent = []
    service = ApiService(
        token=TOKEN,
        speakers=StubRegistry(**speakers),
        default_devices=["parlante"],
        notify=lambda chat_id, text: sent.append((chat_id, text)),
        chat_ids=chats,
        quiet=NIGHT,
        clock=lambda: now,
    )
    return service, speakers, sent


def test_it_speaks_on_the_default_device():
    service, spk, _ = build()

    result = service.say(TOKEN, {"text": "backup terminado"})

    assert spk["parlante"].said == ["backup terminado"]
    assert result["spoken"] is True
    assert result["devices"] == ["parlante"]


def test_a_wrong_token_is_refused_and_nothing_is_said():
    service, spk, _ = build()

    with pytest.raises(Unauthorized):
        service.say("otro-token", {"text": "hola"})

    assert spk["parlante"].said == []


def test_an_empty_token_is_refused():
    service, _, _ = build()

    with pytest.raises(Unauthorized):
        service.say("", {"text": "hola"})


def test_empty_text_is_rejected():
    service, _, _ = build()

    with pytest.raises(ApiError, match="text"):
        service.say(TOKEN, {"text": "   "})


def test_missing_text_is_rejected():
    service, _, _ = build()

    with pytest.raises(ApiError, match="text"):
        service.say(TOKEN, {})


def test_it_can_target_devices():
    service, spk, _ = build()

    service.say(TOKEN, {"text": "hola", "devices": ["comedor"]})

    assert spk["comedor"].said == ["hola"]
    assert spk["parlante"].said == []


def test_an_unknown_device_is_rejected_before_speaking():
    service, spk, _ = build()

    with pytest.raises(ApiError, match="cocina"):
        service.say(TOKEN, {"text": "hola", "devices": ["comedor", "cocina"]})

    assert spk["comedor"].said == []


def test_at_night_it_only_reaches_telegram():
    service, spk, sent = build(now=AT_NIGHT)

    result = service.say(TOKEN, {"text": "backup terminado"})

    assert spk["parlante"].said == []
    assert result["spoken"] is False
    assert len(sent) == 1
    assert "backup terminado" in sent[0][1]


def test_an_urgent_message_wakes_the_house():
    service, spk, _ = build(now=AT_NIGHT)

    result = service.say(TOKEN, {"text": "se cayó produccion", "urgent": True})

    assert spk["parlante"].said == ["se cayó produccion"]
    assert result["spoken"] is True


def test_everyone_on_the_whitelist_gets_the_night_message():
    service, _, sent = build(now=AT_NIGHT, chats=(42, 77))

    service.say(TOKEN, {"text": "hola"})

    assert sorted(chat for chat, _ in sent) == [42, 77]


def test_a_failing_device_is_reported_but_does_not_raise():
    speakers = {"parlante": FakeSpeaker("parlante", RuntimeError("boom"))}
    service = ApiService(
        token=TOKEN,
        speakers=StubRegistry(**speakers),
        default_devices=["parlante"],
        notify=lambda chat_id, text: None,
        chat_ids=(),
        quiet=None,
    )

    with pytest.raises(ApiError):
        service.say(TOKEN, {"text": "hola"})


def test_health_needs_no_token():
    service, _, _ = build()

    health = service.health()

    assert health["ok"] is True
    assert "parlante" in health["devices"]

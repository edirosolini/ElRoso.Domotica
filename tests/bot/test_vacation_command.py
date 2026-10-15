"""/vacaciones: la casa no habla hasta la vuelta, y todo llega por el chat."""

from datetime import datetime

import pytest

from homeauto.bot.commands import Commands, with_actions
from homeauto.quiet import AWAY_END_KEY, AwayStore, Hush, HushStore, QuietHours, Vacation
from homeauto.route import Decision

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
OTHER = 77
STRANGER = 99
NOON = datetime(2026, 10, 15, 12, 0)
BACK = datetime(2026, 10, 25, 0, 0)


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)


class FakeRouter:
    def __init__(self, decision):
        self.decision = decision

    def route(self, _text):
        return self.decision


@pytest.fixture
def house(tmp_path):
    path = tmp_path / "jobs.db"
    hush = Hush(
        hours=QuietHours.parse("22:00", "05:25"),
        store=HushStore(path),
        clock=lambda: NOON,
        away=AwayStore(path),
    )
    timer = FakeTimer()
    sent = []
    vacation = Vacation(
        hush=hush,
        timer=timer,
        notify=lambda chat_id, text: sent.append((chat_id, text)),
        chat_ids=(OWNER, OTHER),
        clock=lambda: NOON,
    )
    speaker = FakeSpeaker("parlante")

    def build(router=None):
        return Commands(
            config=make_config(allowed={OWNER, OTHER}),
            speakers=StubRegistry(parlante=speaker),
            quiet=hush,
            vacation=vacation,
            router=router,
            clock=lambda: NOON,
        )

    return {
        "cmd": build(),
        "build": build,
        "hush": hush,
        "timer": timer,
        "sent": sent,
        "speaker": speaker,
    }


def test_activating_says_until_when_and_arms_the_end(house):
    reply = house["cmd"].vacation(OWNER, "hasta 25/10", who="Eze")

    assert "25/10" in reply
    assert "/vacaciones off" in reply
    assert house["hush"].is_away(NOON) is True
    assert house["timer"].armed[AWAY_END_KEY][0] == BACK


def test_activating_tells_the_other_chats_who_did_it(house):
    house["cmd"].vacation(OWNER, "hasta 25/10", who="Eze")

    assert house["sent"] == [(OTHER, "🧳 Eze activó vacaciones hasta el 25/10")]


def test_an_hour_can_be_given(house):
    house["cmd"].vacation(OWNER, "hasta 25/10 18:00", who="Eze")

    assert house["hush"].away_until(NOON) == datetime(2026, 10, 25, 18, 0)


def test_a_date_that_already_came_is_refused(house):
    reply = house["cmd"].vacation(OWNER, "hasta 15/10", who="Eze")

    assert house["hush"].is_away(NOON) is False
    assert "todavía no llegó" in reply


def test_an_impossible_date_is_refused(house):
    reply = house["cmd"].vacation(OWNER, "hasta 31/02", who="Eze")

    assert house["hush"].is_away(NOON) is False
    assert "no existe" in reply


def test_off_cuts_them_and_tells_the_others(house):
    house["cmd"].vacation(OWNER, "hasta 25/10", who="Eze")
    house["sent"].clear()

    reply = house["cmd"].vacation(OTHER, "off", who="Ana")

    assert "vuelvo a hablar" in reply.lower()
    assert house["hush"].is_away(NOON) is False
    assert AWAY_END_KEY not in house["timer"].armed
    assert house["sent"] == [(OWNER, "🧳 Ana cortó las vacaciones")]


def test_off_without_vacations_says_so(house):
    reply = house["cmd"].vacation(OWNER, "off", who="Eze")

    assert "no estaba" in reply.lower()
    assert house["sent"] == []


def test_without_argument_it_answers_the_state(house):
    assert "/vacaciones hasta" in house["cmd"].vacation(OWNER, "")

    house["cmd"].vacation(OWNER, "hasta 25/10", who="Eze")

    reply = house["cmd"].vacation(OWNER, "")
    assert "De vacaciones hasta el 25/10" in reply
    assert "/vacaciones off" in reply


def test_without_a_date_it_answers_the_state_and_how_and_asks_nothing(house):
    reply = house["cmd"].vacation(OWNER, "nos vamos de vacaciones")

    assert house["hush"].is_away(NOON) is False
    assert "/vacaciones hasta 25/10" in reply
    assert "?" not in reply


def test_the_name_comes_from_who_typed_it(house):
    with_actions(house["cmd"].vacation, OWNER, "hasta 25/10", who="Eze")

    assert house["sent"] == [(OTHER, "🧳 Eze activó vacaciones hasta el 25/10")]


def test_without_a_name_it_is_someone(house):
    house["cmd"].vacation(OWNER, "hasta 25/10")

    assert house["sent"] == [(OTHER, "🧳 Alguien activó vacaciones hasta el 25/10")]


def test_a_stranger_is_refused(house):
    reply = house["cmd"].vacation(STRANGER, "hasta 25/10")

    assert str(STRANGER) in reply
    assert house["hush"].is_away(NOON) is False


def test_without_a_real_hush_it_is_not_configured():
    cmd = Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker()),
        quiet=QuietHours.parse("22:00", "05:25"),
        clock=lambda: NOON,
    )

    assert "no tengo" in cmd.vacation(OWNER, "hasta 25/10").lower()


def test_without_the_notice_it_still_starts_and_stops(tmp_path):
    path = tmp_path / "jobs.db"
    hush = Hush(
        hours=QuietHours.parse("22:00", "05:25"),
        store=HushStore(path),
        clock=lambda: NOON,
        away=AwayStore(path),
    )
    cmd = Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker()),
        quiet=hush,
        clock=lambda: NOON,
    )

    cmd.vacation(OWNER, "hasta 25/10")
    assert hush.is_away(NOON) is True
    cmd.vacation(OWNER, "off")
    assert hush.is_away(NOON) is False


# --- lo que cambia en vacaciones -------------------------------------------------


@pytest.mark.parametrize("run, text", [("say", "hola"), ("call", "a cenar")])
def test_saying_and_calling_refuse_with_the_reason_and_the_way_out(house, run, text):
    house["cmd"].vacation(OWNER, "hasta 25/10", who="Eze")

    reply = getattr(house["cmd"], run)(OWNER, text)

    assert house["speaker"].said == []
    assert "De vacaciones hasta el 25/10" in reply
    assert "/vacaciones off" in reply


def test_the_volume_stop_and_turn_off_keep_working(house):
    house["cmd"].vacation(OWNER, "hasta 25/10", who="Eze")
    house["speaker"].turn_off = lambda: house["speaker"].said.append("(apagado)")

    assert "Volumen en 30" in house["cmd"].volume(OWNER, "30")
    assert "Cortado" in house["cmd"].stop(OWNER, "")
    assert "Apagado" in house["cmd"].turn_off(OWNER, "")


def test_the_silence_status_tells_the_vacations(house):
    house["cmd"].vacation(OWNER, "hasta 25/10", who="Eze")

    assert "De vacaciones hasta el 25/10" in house["cmd"].silence(OWNER, "")


def test_the_silence_status_without_vacations_is_as_always(house):
    assert house["cmd"].silence(OWNER, "").startswith("Estoy hablando.")


def test_speaking_again_does_not_end_the_vacations(house):
    house["cmd"].vacation(OWNER, "hasta 25/10", who="Eze")

    house["cmd"].speak(OWNER, "")

    assert house["hush"].is_away(NOON) is True


def test_free_text_reaches_the_vacations(house):
    cmd = house["build"](router=FakeRouter(Decision("vacaciones", "hasta 25/10")))

    reply = cmd.free_text(OWNER, "nos vamos de vacaciones hasta el 25 de octubre")

    assert "/vacaciones hasta 25/10" in reply
    assert house["hush"].is_away(NOON) is True


def test_vacations_are_reachable_by_name(house):
    assert "vacaciones" in house["cmd"]._dispatch()


# --- el cableado de Telegram ---------------------------------------------------


class _Handlers:
    def __init__(self):
        self.by_name = {}

    def add_handler(self, handler):
        for name in getattr(handler, "commands", ()):
            self.by_name[name] = handler.callback


class _Sent:
    async def edit_text(self, answer, reply_markup=None):
        pass


class _Message:
    def __init__(self, text):
        self.text = text

    async def reply_text(self, answer, reply_markup=None):
        return _Sent()


class _User:
    first_name = "Eze"
    last_name = None
    username = None


class _Update:
    def __init__(self, text, chat_id=OWNER):
        self.message = _Message(text)
        self.effective_chat = type("Chat", (), {"id": chat_id})()
        self.effective_user = _User()


async def test_the_typed_command_carries_the_name_of_who_wrote_it(house):
    from homeauto import main

    app = _Handlers()
    main.register(app, house["cmd"])

    await app.by_name["vacaciones"](_Update("/vacaciones hasta 25/10"), None)

    assert house["sent"] == [(OTHER, "🧳 Eze activó vacaciones hasta el 25/10")]

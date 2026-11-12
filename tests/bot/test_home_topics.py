"""/inicio: los temas como botones, cada uno con los suyos, y los botones que arman un pedido."""

from datetime import datetime

import pytest

from homeauto.ask import Answer
from homeauto.bot.commands import (
    CHATLESS_ONLY,
    MAX_BUTTONS,
    MAX_LABEL,
    TOPICS,
    Commands,
    with_actions,
)
from homeauto.lists import ListStore
from homeauto.pending import Conversation, PendingStore
from homeauto.route import Decision, RouteError

from tests.conftest import FakeSpeaker, StubRegistry, make_config
from tests.bot.test_conversation import FakeReminders, ScriptedRouter

OWNER = 42
FAMILY = 77
NOW = datetime(2026, 9, 4, 10, 0)


class FakeAsker:
    def __init__(self):
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return Answer(spoken="son dos cosas", written="Son dos cosas.")


class FailingRouter:
    def __init__(self):
        self.seen = []

    def route(self, message):
        self.seen.append(message)
        raise RouteError("No te entendí. Probá con /ayuda.")


def build(tmp_path, router=None, conversation=True):
    path = tmp_path / "jobs.db"
    return Commands(
        config=make_config(allowed={OWNER, FAMILY}, alert_chat_ids=frozenset({OWNER})),
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        reminders=FakeReminders(),
        lists=ListStore(path),
        asker=FakeAsker(),
        router=router if router is not None else ScriptedRouter(),
        conversation=Conversation(PendingStore(path), clock=lambda: NOW) if conversation else None,
        clock=lambda: NOW,
    )


def topic_data(reply):
    return [data for _, data in reply.actions if data.startswith("tema ")]


def test_home_offers_the_six_topics_to_the_family(tmp_path):
    reply = with_actions(build(tmp_path).home, FAMILY)

    assert topic_data(reply) == [
        "tema avisos", "tema parlante", "tema comida", "tema hoy", "tema preguntar",
        "tema silencio",
    ]
    assert "¿Qué querés hacer?" in reply.text


def test_home_adds_the_settings_for_an_alert_chat(tmp_path):
    reply = with_actions(build(tmp_path).home, OWNER)

    assert topic_data(reply)[-1] == "tema ajustes"
    assert len(topic_data(reply)) == 7


def test_start_is_the_home(tmp_path):
    cmd = build(tmp_path)

    assert with_actions(cmd.start, FAMILY) == with_actions(cmd.home, FAMILY)


def test_a_stranger_does_not_get_the_topics(tmp_path):
    reply = with_actions(build(tmp_path).home, 99)

    assert "No estás en la lista" in reply.text
    assert reply.actions == ()


@pytest.mark.parametrize("key", ["avisos", "parlante", "comida", "hoy", "preguntar", "silencio"])
def test_each_topic_opens_its_buttons_and_a_way_back(tmp_path, key):
    reply = with_actions(build(tmp_path).press, FAMILY, f"tema {key}")

    assert len(reply.actions) > 1
    assert reply.actions[-1][1] == "inicio"
    assert TOPICS[key][0] in reply.text


def test_the_reminders_topic_has_its_three_ways_to_set_one(tmp_path):
    reply = with_actions(build(tmp_path).press, FAMILY, "tema avisos")

    data = [data for _, data in reply.actions]
    assert data[:6] == [
        "armar timer", "armar alarma", "armar recordar", "lista", "pastillas", "turnos",
    ]


def test_the_settings_open_for_an_alert_chat(tmp_path):
    reply = with_actions(build(tmp_path).press, OWNER, "tema ajustes")

    data = [data for _, data in reply.actions]
    assert "depurar" in data and "armar usar" in data


def test_the_settings_do_not_open_for_the_family(tmp_path):
    reply = with_actions(build(tmp_path).press, FAMILY, "tema ajustes")

    assert reply.actions == ()
    assert "ajustes" not in reply.text.lower()
    assert reply.text == with_actions(build(tmp_path).press, FAMILY, "tema nada").text


def test_every_button_fits_in_telegram():
    for label, actions in TOPICS.values():
        assert len(label) <= MAX_LABEL
        assert len(actions) + 1 <= MAX_BUTTONS
        for text, data in actions:
            assert len(text) <= MAX_LABEL
            assert len(data.encode()) <= 64
    assert len(TOPICS) <= MAX_BUTTONS


def test_every_topic_button_runs_something_known(tmp_path):
    cmd = build(tmp_path)
    for _, actions in TOPICS.values():
        for _, data in actions:
            command, _, argument = data.partition(" ")
            if command == "armar":
                assert argument in cmd._dispatch(), data
            else:
                assert command in cmd._dispatch(), data


def test_home_can_be_typed_with_a_slash(tmp_path):
    assert build(tmp_path).typed("inicio")


def test_the_back_button_goes_home(tmp_path):
    cmd = build(tmp_path)

    assert with_actions(cmd.press, FAMILY, "inicio") == with_actions(cmd.home, FAMILY)


@pytest.mark.parametrize("data", ["tema avisos", "inicio", "armar alarma"])
def test_without_telegram_a_topic_is_not_offered(tmp_path, data):
    assert build(tmp_path).press_without_chat(data) == CHATLESS_ONLY


def test_a_message_it_did_not_get_offers_the_topics_and_not_the_help(tmp_path):
    router = FailingRouter()
    cmd = build(tmp_path, router=router)

    reply = with_actions(cmd.free_text, FAMILY, "apagá la tele")

    assert "/ayuda" not in reply.text
    assert topic_data(reply)
    assert cmd.asker.asked == []


def test_without_a_router_it_offers_the_topics(tmp_path):
    cmd = build(tmp_path)
    cmd.router = None

    reply = with_actions(cmd.free_text, FAMILY, "cómo viene el tiempo")

    assert "/ayuda" not in reply.text
    assert topic_data(reply)


def test_an_alarm_button_asks_the_time_without_the_model(tmp_path):
    router = ScriptedRouter()
    cmd = build(tmp_path, router=router)

    reply = with_actions(cmd.press, FAMILY, "armar alarma")

    assert reply.text == "¿A qué hora?"
    assert router.seen == []
    assert cmd.conversation.get(FAMILY).command == "alarma"


def test_the_answer_to_an_armed_timer_schedules_it(tmp_path):
    router = ScriptedRouter(Decision(None), Decision("timer", "10m sacar la pizza"))
    cmd = build(tmp_path, router=router)
    cmd.press(FAMILY, "armar timer")

    reply = cmd.free_text(FAMILY, "en 10 minutos sacar la pizza")

    assert len(cmd.reminders.added) == 1
    assert cmd.reminders.added[0][2] == "sacar la pizza"
    assert router.seen[-1].endswith("\nen 10 minutos sacar la pizza")
    assert cmd.conversation.get(FAMILY) is None
    assert reply


def test_the_answer_to_an_armed_item_goes_straight_to_the_list(tmp_path):
    router = ScriptedRouter()
    cmd = build(tmp_path, router=router)
    assert cmd.press(FAMILY, "armar agregar") == "¿Qué agrego?"

    cmd.free_text(FAMILY, "leche")

    assert router.seen == [], "la respuesta ya es el argumento: no paga el modelo"
    assert cmd.lists.items("compras") == ["leche"]
    assert cmd.conversation.get(FAMILY) is None


def test_the_answer_to_an_armed_question_is_asked(tmp_path):
    cmd = build(tmp_path)
    cmd.press(FAMILY, "armar preguntar")

    reply = cmd.free_text(FAMILY, "cuántos goles hizo Messi")

    assert cmd.asker.asked == ["cuántos goles hizo Messi"]
    assert "Son dos cosas." in reply


def test_an_armed_one_can_be_dropped(tmp_path):
    cmd = build(tmp_path)
    cmd.press(FAMILY, "armar decir")

    cmd.free_text(FAMILY, "olvidalo")

    assert cmd.conversation.get(FAMILY) is None


def test_an_unknown_one_is_not_armed(tmp_path):
    cmd = build(tmp_path)

    reply = cmd.press(FAMILY, "armar lista")

    assert cmd.conversation.get(FAMILY) is None
    assert "botón" in reply

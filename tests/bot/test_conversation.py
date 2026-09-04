"""El bot pregunta lo que falta en vez de contestar un error de parser.

Decisión del dueño: **solo pregunta cuando falta un dato obligatorio**. Un
mensaje completo se ejecuta de una, como siempre.
"""

from datetime import datetime

import pytest

from homeauto import slots
from homeauto.ask import Answer
from homeauto.bot.commands import Commands
from homeauto.pending import Conversation, PendingStore
from homeauto.route import Decision, RouteError

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
NOW = datetime(2026, 9, 4, 10, 0)


class ScriptedRouter:
    """Contesta según lo que ya vio, para poder guionar una conversación."""

    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.seen = []

    def route(self, message):
        self.seen.append(message)
        if not self.decisions:
            return Decision(None)
        return self.decisions.pop(0)


class FakeReminders:
    def __init__(self):
        self.added = []

    def add(self, chat_id, when, message, repeat="once", device="", days=None):
        self.added.append((chat_id, when, message, repeat, days))

        class Job:
            id = len(self.added)

        return Job()


class FakeAsker:
    def __init__(self):
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return Answer(spoken="son dos cosas", written="Son dos cosas.")


class FakeWeather:
    def spoken(self):
        return "Ahora hay catorce grados."


def build(tmp_path, router, conversation=True):
    speakers = {"parlante": FakeSpeaker("parlante")}
    talk = None
    if conversation:
        talk = Conversation(PendingStore(tmp_path / "jobs.db"), clock=lambda: NOW)
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        reminders=FakeReminders(),
        weather=FakeWeather(),
        asker=FakeAsker(),
        router=router,
        conversation=talk,
        clock=lambda: NOW,
    )
    return commands, speakers, talk


def test_an_alarm_without_data_asks_instead_of_failing(tmp_path):
    router = ScriptedRouter(Decision("alarma", ""))
    cmd, _, talk = build(tmp_path, router)

    reply = cmd.free_text(OWNER, "creá una alarma")

    assert "hora" in reply.lower()
    assert cmd.reminders.added == []
    assert talk.get(OWNER).command == "alarma"


def test_the_answer_continues_the_same_command(tmp_path):
    router = ScriptedRouter(
        Decision("alarma", ""),        # "creá una alarma"
        Decision(None),                # "a las 7", suelto, no es un comando
        Decision("alarma", "7:00"),    # el hilo entero
    )
    cmd, _, _ = build(tmp_path, router)
    cmd.free_text(OWNER, "creá una alarma")

    reply = cmd.free_text(OWNER, "a las 7")

    assert "creá una alarma\na las 7" in router.seen
    assert "diga" in reply.lower()


def test_a_finished_conversation_runs_the_command(tmp_path):
    router = ScriptedRouter(
        Decision("alarma", ""),
        Decision(None),
        Decision("alarma", "7:00"),
        Decision(None),
        Decision("alarma", "7:00 arriba"),
        Decision(None),
        Decision("alarma", "diaria 7:00 arriba"),
    )
    cmd, _, talk = build(tmp_path, router)
    cmd.free_text(OWNER, "creá una alarma")
    cmd.free_text(OWNER, "a las 7")
    cmd.free_text(OWNER, "arriba")

    reply = cmd.free_text(OWNER, "todos los días")

    assert "/alarma diaria 7:00 arriba" in reply
    assert [a[2] for a in cmd.reminders.added] == ["arriba"]
    assert talk.get(OWNER) is None


def test_a_complete_message_still_runs_without_asking(tmp_path):
    """Lo de siempre: si no falta nada, no hay conversación."""
    router = ScriptedRouter(Decision("clima"))
    cmd, spk, talk = build(tmp_path, router)

    reply = cmd.free_text(OWNER, "dame el clima")

    assert spk["parlante"].said == ["Ahora hay catorce grados."]
    assert "Entendí: /clima" in reply
    assert talk.get(OWNER) is None


def test_another_complete_command_wins_over_what_was_pending(tmp_path):
    """«dame el clima» en medio de una alarma es un comando, no una respuesta."""
    router = ScriptedRouter(Decision("alarma", ""), Decision("clima"))
    cmd, spk, talk = build(tmp_path, router)
    cmd.free_text(OWNER, "creá una alarma")

    reply = cmd.free_text(OWNER, "dame el clima")

    assert spk["parlante"].said == ["Ahora hay catorce grados."]
    assert talk.get(OWNER) is None
    assert "alarma" in reply.lower()  # avisa que la dejó a medio armar


def test_a_word_that_drops_it_costs_no_model_call(tmp_path):
    router = ScriptedRouter(Decision("alarma", ""))
    cmd, _, talk = build(tmp_path, router)
    cmd.free_text(OWNER, "creá una alarma")

    reply = cmd.free_text(OWNER, "olvidalo")

    assert router.seen == ["creá una alarma"]
    assert talk.get(OWNER) is None
    assert "dejo" in reply.lower()


def test_a_slot_is_never_asked_twice(tmp_path):
    """Preguntar lo mismo otra vez es un loop; el parser lo explica mejor."""
    router = ScriptedRouter(
        Decision("alarma", ""),
        Decision(None),
        Decision("alarma", ""),  # el hilo no aportó la hora
    )
    cmd, _, talk = build(tmp_path, router)
    cmd.free_text(OWNER, "creá una alarma")

    reply = cmd.free_text(OWNER, "cualquier cosa")

    assert "Falta" in reply
    assert cmd.reminders.added == []
    assert talk.get(OWNER) is None


def test_without_a_conversation_it_behaves_like_before(tmp_path):
    """Sin store, un comando incompleto sale con el error del parser."""
    router = ScriptedRouter(Decision("alarma", ""))
    cmd, _, _ = build(tmp_path, router, conversation=False)

    reply = cmd.free_text(OWNER, "creá una alarma")

    assert "Falta" in reply
    assert cmd.reminders.added == []


def test_a_question_is_still_a_question(tmp_path):
    router = ScriptedRouter(Decision(None))
    cmd, _, talk = build(tmp_path, router)

    reply = cmd.free_text(OWNER, "cuántos goles hizo Messi")

    assert "Son dos cosas." in reply
    assert talk.get(OWNER) is None


@pytest.mark.parametrize(
    "command, argument",
    [
        ("alarma", ""),
        ("alarma", "7:30"),
        ("alarma", "diaria"),
        ("alarma", "diaria 7:30"),
        ("alarma", "lun-vie"),
        ("alarma", "lun-vie 5:30"),
        ("timer", ""),
        ("timer", "10m"),
        ("decir", ""),
        ("cancelar", ""),
        ("volumen", ""),
        ("usar", ""),
    ],
)
def test_what_slots_calls_incomplete_the_real_command_refuses(tmp_path, command, argument):
    """Ata `slots` a los comandos de verdad.

    La forma de una alarma se mira en dos lados: `slots.missing()` y
    `Commands.alarm`. Si se separan, el bot pregunta por algo que ya tenía o
    ejecuta algo que no puede. Queda afuera la repetición: una alarma de una
    sola vez el parser la acepta, preguntarla es decisión del dueño.
    """
    assert slots.missing(command, argument) is not None

    cmd, spk, _ = build(tmp_path, ScriptedRouter())
    reply = cmd._dispatch()[command](OWNER, argument)

    assert cmd.reminders.added == []
    assert spk["parlante"].said == []
    assert spk["parlante"].volumes == []
    assert reply


class BrokenRouter:
    """El modelo no contesta: ni una interpretación ni una excusa útil."""

    def __init__(self, *decisions):
        self.decisions = list(decisions)

    def route(self, message):
        if self.decisions:
            return self.decisions.pop(0)
        raise RouteError("No te entendí. Probá con /ayuda.")


def test_a_model_that_falls_over_mid_conversation_does_not_web_search(tmp_path):
    """🔴 Que el intérprete falle no convierte «a las 7» en una pregunta."""
    cmd, _, talk = build(tmp_path, BrokenRouter(Decision("alarma", "")))
    cmd.free_text(OWNER, "creá una alarma")

    reply = cmd.free_text(OWNER, "a las 7")

    assert "/ayuda" in reply
    assert cmd.asker.asked == []
    assert talk.get(OWNER).command == "alarma"


def test_a_model_that_falls_over_with_nothing_pending_says_so(tmp_path):
    cmd, _, _ = build(tmp_path, BrokenRouter())

    reply = cmd.free_text(OWNER, "apagá la tele")

    assert "/ayuda" in reply
    assert cmd.asker.asked == []

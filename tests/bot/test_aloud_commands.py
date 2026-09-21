"""El parlante dejó de ser el destino por defecto: se pide."""

from homeauto.ask import Answer
from homeauto.bot.commands import Commands
from homeauto.route import Decision

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42


class FakeWeather:
    def spoken(self):
        return "Ahora hay catorce grados."


class FakeAgenda:
    def spoken(self, when=""):
        return "Hoy tenés una cosa."


class FakeAsker:
    def ask(self, question):
        return Answer(spoken="son dos", written="Son dos, y algo más largo.")


class FakeRouter:
    def __init__(self, decision):
        self.decision = decision
        self.seen = []

    def route(self, message):
        self.seen.append(message)
        return self.decision


def build(router=None):
    speakers = {"parlante": FakeSpeaker("parlante")}
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        weather=FakeWeather(),
        agenda=FakeAgenda(),
        asker=FakeAsker(),
        router=router,
    )
    return commands, speakers


def test_the_weather_only_answers_in_writing():
    cmd, spk = build()

    reply = cmd.weather(OWNER, "")

    assert spk["parlante"].said == []
    assert "catorce grados" in reply


def test_the_weather_speaks_when_it_is_asked_for():
    cmd, spk = build()

    cmd.weather(OWNER, "por el parlante")

    assert spk["parlante"].said == ["Ahora hay catorce grados."]


def test_the_agenda_only_answers_in_writing():
    cmd, spk = build()

    cmd.agenda_command(OWNER, "")

    assert spk["parlante"].said == []


def test_the_agenda_speaks_when_it_is_asked_for():
    cmd, spk = build()

    cmd.agenda_command(OWNER, "mañana en voz alta")

    assert spk["parlante"].said == ["Hoy tenés una cosa."]


def test_a_question_is_answered_in_writing_and_whole():
    cmd, spk = build()

    reply = cmd.ask(OWNER, "cuántos son")

    assert spk["parlante"].said == []
    assert "Son dos, y algo más largo." in reply


def test_a_question_is_spoken_when_it_is_asked_for():
    cmd, spk = build()

    cmd.ask(OWNER, "cuántos son por el parlante")

    assert spk["parlante"].said == ["son dos"]


def test_saying_something_always_comes_out_of_the_speaker():
    """/decir es pedir que hable: no hace falta decírselo dos veces."""
    cmd, spk = build()

    cmd.say(OWNER, "la cena está lista")

    assert spk["parlante"].said == ["la cena está lista"]


def test_calling_the_house_always_comes_out_of_the_speaker():
    cmd, spk = build()

    cmd.call(OWNER, "a cenar")

    assert spk["parlante"].said


def test_free_text_does_not_speak_either():
    cmd, spk = build(router=FakeRouter(Decision("clima")))

    cmd.free_text(OWNER, "cómo viene el clima")

    assert spk["parlante"].said == []


def test_free_text_speaks_when_the_message_asks_for_it():
    router = FakeRouter(Decision("clima"))
    cmd, spk = build(router=router)

    cmd.free_text(OWNER, "cómo viene el clima por el parlante")

    assert spk["parlante"].said == ["Ahora hay catorce grados."]
    assert router.seen == ["cómo viene el clima"], "la coletilla no va al modelo"

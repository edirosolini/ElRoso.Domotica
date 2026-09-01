"""El comando que contesta preguntas.

Sigue el camino de /clima: consulta algo y lo dice. La diferencia es que lo
dicho y lo escrito no son el mismo texto.
"""

from homeauto.ask import Answer, AskError, NOT_SPOKEN
from homeauto.bot.commands import Commands
from homeauto.quiet import QuietHours

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42


class FakeAsker:
    def __init__(self, answer=None, boom=None):
        self.answer = answer or Answer(
            spoken="El del Getafe encabeza la lista.",
            written="Los diez mejores goles de Messi. Encabeza el del Getafe, de 2007.",
        )
        self.boom = boom
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        if self.boom:
            raise self.boom
        return self.answer


def build(asker="default", quiet=None, **speakers):
    speakers = speakers or {"parlante": FakeSpeaker("parlante")}
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        asker=FakeAsker() if asker == "default" else asker,
        quiet=quiet,
    )
    return commands, speakers


def test_it_answers_out_loud_and_writes_the_full_answer():
    cmd, spk = build()

    reply = cmd.ask(OWNER, "top 10 de los mejores goles de Messi")

    assert spk["parlante"].said == ["El del Getafe encabeza la lista."]
    assert "2007" in reply, "al chat va la respuesta entera, con los números"


def test_the_question_travels_whole():
    asker = FakeAsker()
    cmd, _ = build(asker=asker)

    cmd.ask(OWNER, "cuántos goles hizo Messi")

    assert asker.asked == ["cuántos goles hizo Messi"]


def test_without_a_question_it_says_how_to_use_it():
    cmd, spk = build()

    reply = cmd.ask(OWNER, "")

    assert "/preguntar" in reply
    assert spk["parlante"].said == []


def test_without_a_key_it_says_so_instead_of_breaking():
    cmd, spk = build(asker=None)

    reply = cmd.ask(OWNER, "algo")

    assert "LLM_API_KEY" in reply
    assert spk["parlante"].said == []


def test_a_failure_is_a_sentence_not_a_traceback():
    cmd, spk = build(asker=FakeAsker(boom=AskError("No pude averiguarlo ahora.")))

    reply = cmd.ask(OWNER, "algo")

    assert reply == "No pude averiguarlo ahora."
    assert spk["parlante"].said == []


def test_during_quiet_hours_it_only_writes():
    """La regla de descanso vale también para una pregunta hecha a mano."""
    from datetime import datetime

    cmd, spk = build(quiet=QuietHours.parse("23:00", "07:00"))
    cmd.clock = lambda: datetime(2026, 9, 1, 3, 0)

    reply = cmd.ask(OWNER, "algo")

    assert spk["parlante"].said == []
    assert "2007" in reply, "la respuesta igual llega escrita"
    assert "descanso" in reply.lower()


def test_an_answer_that_cannot_be_spoken_is_only_written():
    """🔴 Si la voz trae dígitos, el parlante no dice nada: no se lee un número mal."""
    asker = FakeAsker(answer=Answer(spoken=NOT_SPOKEN, written="Messi hizo 672 goles."))
    cmd, spk = build(asker=asker)

    reply = cmd.ask(OWNER, "cuántos goles")

    assert spk["parlante"].said == [NOT_SPOKEN]
    assert "672" in reply


def test_it_goes_to_the_device_you_asked_for():
    parlante, comedor = FakeSpeaker("parlante"), FakeSpeaker("comedor")
    cmd, _ = build(parlante=parlante, comedor=comedor)

    cmd.ask(OWNER, "en comedor cuántos goles hizo Messi")

    assert comedor.said and parlante.said == []

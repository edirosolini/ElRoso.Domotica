"""`/traducir`: la traducción se lee, no se escucha."""

from homeauto.bot.commands import Commands
from homeauto.translate import TranslateError, Translator

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42


class FakeTranslator:
    def __init__(self, answer="hello", boom=None):
        self.answer = answer
        self.boom = boom
        self.asked = []

    def translate(self, text):
        self.asked.append(text)
        if self.boom:
            raise self.boom
        return self.answer


def build(translator=None):
    speakers = {"parlante": FakeSpeaker("parlante")}
    commands = Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(**speakers),
        translator=translator if translator is not None else FakeTranslator(),
    )
    return commands, speakers


def test_it_answers_with_the_translation():
    cmd, _ = build()

    assert cmd.translate(OWNER, "hola") == "hello"


def test_the_text_travels_whole():
    translator = FakeTranslator()
    cmd, _ = build(translator)

    cmd.translate(OWNER, "al francés hola qué tal")

    assert translator.asked == ["al francés hola qué tal"], "el idioma lo resuelve el traductor"


def test_it_never_reaches_the_speaker():
    """🔴 Piper habla es_AR: leería el inglés con fonética española."""
    cmd, spk = build()

    reply = cmd.translate(OWNER, "hola por el parlante")

    assert spk["parlante"].said == []
    assert "hello" in reply
    assert "no lo digo" in reply.lower()


def test_without_text_it_says_how_to_use_it():
    cmd, _ = build()

    assert "/traducir" in cmd.translate(OWNER, "")


def test_a_translator_that_fails_is_answered_not_crashed():
    cmd, _ = build(FakeTranslator(boom=TranslateError("No pude traducir: sin red")))

    reply = cmd.translate(OWNER, "hola")

    assert "no pude traducir" in reply.lower()


def test_without_a_key_it_says_what_is_missing():
    commands = Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
    )

    assert "LLM_API_KEY" in commands.translate(OWNER, "hola")


def test_a_stranger_gets_nothing():
    translator = FakeTranslator()
    cmd, _ = build(translator)

    cmd.translate(999, "hola")

    assert translator.asked == []

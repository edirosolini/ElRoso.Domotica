"""Una nota de voz convertida en el texto que la persona dijo."""

import pytest

from homeauto.listen import ListenError, Transcriber

AUDIO = b"OggS\x00fake"


class FakeModel:
    def __init__(self, *answers, fail=False):
        self.answers = list(answers)
        self.fail = fail
        self.calls = []

    def __call__(self, prompt, audio=None, mime=None):
        self.calls.append((prompt, audio, mime))
        if self.fail:
            raise RuntimeError("la API no contestó")
        return self.answers.pop(0) if self.answers else ""


def test_it_returns_what_was_said():
    model = FakeModel("poneme una alarma a las siete")

    assert Transcriber(model)(AUDIO) == "poneme una alarma a las siete"


def test_the_audio_goes_with_the_prompt():
    model = FakeModel("hola")

    Transcriber(model)(AUDIO)

    _, audio, mime = model.calls[0]
    assert audio == AUDIO
    assert mime == "audio/ogg"


def test_a_model_that_fails_is_not_a_transcription():
    with pytest.raises(ListenError):
        Transcriber(FakeModel(fail=True))(AUDIO)


def test_an_empty_answer_is_not_a_transcription():
    with pytest.raises(ListenError):
        Transcriber(FakeModel("   "))(AUDIO)


def test_the_word_for_nothing_understood_is_not_a_transcription():
    with pytest.raises(ListenError):
        Transcriber(FakeModel("NADA"))(AUDIO)


def test_a_speech_is_not_an_order():
    with pytest.raises(ListenError):
        Transcriber(FakeModel("palabra " * 200))(AUDIO)


def test_quotes_around_the_answer_are_dropped():
    assert Transcriber(FakeModel('«poneme una alarma»'))(AUDIO) == "poneme una alarma"


def test_the_prompt_asks_for_a_literal_transcription():
    model = FakeModel("hola")

    Transcriber(model)(AUDIO)

    prompt = model.calls[0][0].lower()
    assert "literal" in prompt
    assert "no" in prompt

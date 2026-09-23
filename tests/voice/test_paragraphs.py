"""Un texto en párrafos se dice con una pausa de punto y aparte entre ellos."""

import wave
from pathlib import Path

import pytest

from homeauto.voice.tts import DEFAULT_SENTENCE_SILENCE, VoiceSynth

RATE = 1000


def seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        return source.getnframes() / source.getframerate()


class OneSecondRunner:
    """Escribe un segundo de audio por llamada y guarda qué le pidieron decir."""

    def __init__(self):
        self.texts = []

    def __call__(self, text: str, out_path: Path) -> None:
        self.texts.append(text)
        with wave.open(str(out_path), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(RATE)
            target.writeframes(b"\x01\x00" * RATE)


def synth(tmp_path, runner, **kwargs):
    return VoiceSynth(tmp_path, runner=runner, min_seconds=0, **kwargs)


def test_each_paragraph_is_synthesized_on_its_own(tmp_path):
    runner = OneSecondRunner()

    synth(tmp_path, runner).say("Hoy tenés dentista.\n\nHace frío.\n\nEl dólar sube.")

    assert runner.texts == ["Hoy tenés dentista.", "Hace frío.", "El dólar sube."]


def test_the_paragraphs_are_joined_with_a_pause(tmp_path):
    clip = synth(tmp_path, OneSecondRunner(), paragraph_silence=2.0).say("Uno.\n\nDos.")

    assert seconds(clip) == pytest.approx(1 + 2.0 + 1)


def test_the_pause_between_paragraphs_is_longer_than_between_sentences(tmp_path):
    from homeauto.voice.tts import DEFAULT_PARAGRAPH_SILENCE

    assert DEFAULT_PARAGRAPH_SILENCE > DEFAULT_SENTENCE_SILENCE


def test_a_single_line_goes_to_the_runner_as_always(tmp_path):
    runner = OneSecondRunner()

    clip = synth(tmp_path, runner).say("  Hace frío.  ")

    assert runner.texts == ["Hace frío."]
    assert seconds(clip) == pytest.approx(1)


def test_blank_lines_do_not_add_pauses(tmp_path):
    runner = OneSecondRunner()

    clip = synth(tmp_path, runner, paragraph_silence=2.0).say("Uno.\n\n\n  \nDos.\n")

    assert runner.texts == ["Uno.", "Dos."]
    assert seconds(clip) == pytest.approx(4)


def test_the_pause_belongs_in_the_cache_key(tmp_path):
    corta = synth(tmp_path, OneSecondRunner(), paragraph_silence=1.0)
    larga = synth(tmp_path, OneSecondRunner(), paragraph_silence=3.0)

    assert corta.say("Uno.\n\nDos.") != larga.say("Uno.\n\nDos.")


def test_the_pause_does_not_touch_the_cache_of_a_single_line(tmp_path):
    """Lo ya sintetizado de una línea sigue sirviendo."""
    corta = synth(tmp_path, OneSecondRunner(), paragraph_silence=1.0)
    larga = synth(tmp_path, OneSecondRunner(), paragraph_silence=3.0)

    assert corta.say("Hace frío.") == larga.say("Hace frío.")


def test_paragraphs_are_cached_like_anything_else(tmp_path):
    runner = OneSecondRunner()
    voice = synth(tmp_path, runner)

    voice.say("Uno.\n\nDos.")
    voice.say("Uno.\n\nDos.")

    assert len(runner.texts) == 2


def test_the_chime_goes_before_the_first_paragraph_only(tmp_path):
    from homeauto.voice import chime

    clip = synth(tmp_path, OneSecondRunner(), paragraph_silence=2.0).say("Uno.\n\nDos.", chime=True)

    assert seconds(clip) == pytest.approx(1 + 2.0 + 1 + chime.SECONDS, abs=0.01)


def test_no_partial_file_is_left_behind(tmp_path):
    synth(tmp_path, OneSecondRunner()).say("Uno.\n\nDos.")

    assert not list(tmp_path.glob("*.partial*"))

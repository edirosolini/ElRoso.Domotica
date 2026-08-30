import wave
from pathlib import Path

import pytest

from homeauto.voice.tts import TtsError, VoiceSynth

SAMPLE_RATE = 22050


def write_wav(path: Path, seconds: float, rate: int = SAMPLE_RATE) -> None:
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * frames)


def duration_of(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


class FakePiper:
    """Stands in for the piper subprocess; records calls and emits a wav."""

    def __init__(self, seconds=3.0, fail=False):
        self.seconds = seconds
        self.fail = fail
        self.calls = []

    def __call__(self, text: str, out_path: Path) -> None:
        self.calls.append((text, out_path))
        if self.fail:
            raise TtsError("piper explotó")
        write_wav(out_path, self.seconds)


@pytest.fixture
def synth(tmp_path):
    def build(piper):
        return VoiceSynth(cache_dir=tmp_path / "cache", runner=piper, min_seconds=1.0)
    return build


def test_synthesizes_and_returns_a_playable_wav(synth):
    piper = FakePiper(seconds=3.0)
    path = synth(piper).say("hola")

    assert path.is_file()
    assert path.suffix == ".wav"
    assert len(piper.calls) == 1
    assert piper.calls[0][0] == "hola"


def test_same_text_is_synthesized_once(synth):
    piper = FakePiper()
    s = synth(piper)

    first = s.say("hola")
    second = s.say("hola")

    assert first == second
    assert len(piper.calls) == 1, "la segunda vez tiene que salir del cache"


def test_different_text_produces_different_files(synth):
    piper = FakePiper()
    s = synth(piper)

    assert s.say("hola") != s.say("chau")
    assert len(piper.calls) == 2


def test_short_audio_is_padded_to_the_minimum(synth):
    piper = FakePiper(seconds=0.3)
    path = synth(piper).say("hola")

    assert duration_of(path) >= 1.0


def test_long_audio_is_left_alone(synth):
    piper = FakePiper(seconds=3.0)
    path = synth(piper).say("una frase larga")

    assert duration_of(path) == pytest.approx(3.0, abs=0.05)


def test_padding_keeps_the_wav_readable(synth):
    piper = FakePiper(seconds=0.2)
    path = synth(piper).say("hola")

    with wave.open(str(path)) as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == SAMPLE_RATE


def test_empty_text_is_rejected(synth):
    with pytest.raises(TtsError, match="vacío"):
        synth(FakePiper()).say("   ")


def test_runner_failure_does_not_leave_a_cached_file(synth):
    piper = FakePiper(fail=True)
    s = synth(piper)

    with pytest.raises(TtsError):
        s.say("hola")

    piper.fail = False
    s.say("hola")
    assert len(piper.calls) == 2, "el fallo no debe quedar cacheado"

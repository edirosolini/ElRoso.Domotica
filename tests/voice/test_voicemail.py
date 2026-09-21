"""La respuesta convertida en nota de voz para el chat."""

import wave
from pathlib import Path

import pytest

from homeauto.voice.voicemail import OpusEncoder, Voicemail, VoicemailError


class FakeSynth:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.said = []

    def say(self, text, chime=False):
        self.said.append(text)
        path = self.cache_dir / f"{abs(hash(text))}.wav"
        with wave.open(str(path), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(22050)
            target.writeframes(b"\x00" * 2 * 22050)
        return path


class FakeEncoder:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, wav: Path, ogg: Path) -> None:
        self.calls.append((wav, ogg))
        if self.fail:
            raise VoicemailError("opusenc no está")
        ogg.write_bytes(b"OggS")


def test_it_returns_an_ogg_next_to_the_wav(tmp_path):
    synth = FakeSynth(tmp_path)
    mail = Voicemail(synth, encode=FakeEncoder())

    path = mail("la cena está lista")

    assert path.suffix == ".ogg"
    assert path.read_bytes() == b"OggS"


def test_a_second_ask_reuses_the_encoded_file(tmp_path):
    encoder = FakeEncoder()
    mail = Voicemail(FakeSynth(tmp_path), encode=encoder)

    first = mail("hola")
    again = mail("hola")

    assert first == again
    assert len(encoder.calls) == 1


def test_an_encoder_that_fails_is_reported(tmp_path):
    mail = Voicemail(FakeSynth(tmp_path), encode=FakeEncoder(fail=True))

    with pytest.raises(VoicemailError):
        mail("hola")


def test_the_real_encoder_calls_opusenc(tmp_path):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return type("Done", (), {"returncode": 0, "stderr": ""})()

    OpusEncoder(run=run)(tmp_path / "a.wav", tmp_path / "a.ogg")

    assert calls[0][0] == "opusenc"
    assert str(tmp_path / "a.ogg") in calls[0]


def test_an_encoder_that_is_not_installed_is_reported(tmp_path):
    def run(args, **kwargs):
        raise FileNotFoundError("opusenc")

    with pytest.raises(VoicemailError):
        OpusEncoder(run=run)(tmp_path / "a.wav", tmp_path / "a.ogg")

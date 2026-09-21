"""The beeps that go in front of an alarm."""

import wave

import pytest

from homeauto.voice import chime


def write_wav(path, frames=b"\x11\x22" * 2205, width=2, rate=22050, channels=1):
    with wave.open(str(path), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(width)
        target.setframerate(rate)
        target.writeframes(frames)
    return path


def read(path):
    with wave.open(str(path), "rb") as source:
        return source.getparams(), source.readframes(source.getnframes())


def test_the_chime_lasts_what_its_parts_add_up_to():
    frames = chime.frames(rate=22050, width=2, channels=1)

    assert len(frames) / (22050 * 2) == pytest.approx(chime.SECONDS, abs=0.01)


def test_the_chime_is_not_silence():
    frames = chime.frames(rate=22050, width=2, channels=1)

    assert any(byte for byte in frames)


def test_it_follows_the_wav_format_it_is_given():
    stereo = chime.frames(rate=8000, width=2, channels=2)

    assert len(stereo) == len(chime.frames(rate=8000, width=2, channels=1)) * 2


def test_prepend_leaves_the_voice_at_the_end(tmp_path):
    voice = b"\x11\x22" * 2205
    path = write_wav(tmp_path / "say.wav", frames=voice)

    chime.prepend(path)

    params, frames = read(path)
    assert frames.endswith(voice)
    assert params.framerate == 22050 and params.sampwidth == 2
    assert len(frames) > len(voice)


def test_an_unsupported_sample_width_says_it_without_beeps(tmp_path):
    voice = b"\x11" * 2205
    path = write_wav(tmp_path / "say.wav", frames=voice, width=1)

    chime.prepend(path)

    _, frames = read(path)
    assert frames == voice

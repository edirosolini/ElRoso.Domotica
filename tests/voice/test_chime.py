"""The beeps that go in front of an alarm."""

import array
import hashlib
import math
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


def test_the_soft_chime_is_a_single_short_tone():
    soft = chime.frames(rate=22050, width=2, channels=1, beeps=chime.SOUNDS[chime.SOFT])
    alarm = chime.frames(rate=22050, width=2, channels=1, beeps=chime.SOUNDS[chime.ALARM])

    assert 0 < len(soft) < len(alarm)
    assert sum(1 for hertz, *_ in chime.SOUNDS[chime.SOFT] if hertz) == 1


def test_true_still_means_the_alarm_beeps():
    assert chime.sound(True) == chime.ALARM
    assert chime.sound(False) is None
    assert chime.sound(chime.SOFT) == chime.SOFT


# --- el despertador ------------------------------------------------------------

RATE = 22050


def samples(name):
    return array.array("h", chime.frames(rate=RATE, width=2, channels=1, beeps=chime.SOUNDS[name]))


def rms(values):
    return math.sqrt(sum(value * value for value in values) / len(values))


def test_the_alarm_and_soft_beeps_did_not_change():
    alarm = chime.frames(rate=RATE, width=2, channels=1, beeps=chime.SOUNDS[chime.ALARM])
    soft = chime.frames(rate=RATE, width=2, channels=1, beeps=chime.SOUNDS[chime.SOFT])

    assert hashlib.sha256(alarm).hexdigest() == (
        "8d7caea5fcbb738b35d7803dee1e6364fde0c2c725413e2dd6fd723334c64215"
    )
    assert hashlib.sha256(soft).hexdigest() == (
        "4e293ac5f92973b638970e1b31b4aed5a25acb11b358e804eb117c04053618b8"
    )


def test_there_are_three_wake_levels_and_the_first_is_the_wake_sound():
    assert len(chime.WAKE_LEVELS) == 3
    assert chime.WAKE == chime.WAKE_LEVELS[0]
    assert all(chime.sound(level) == level for level in chime.WAKE_LEVELS)


def test_each_wake_level_is_longer_and_louder_than_the_one_before():
    levels = [samples(level) for level in chime.WAKE_LEVELS]

    for quieter, louder in zip(levels, levels[1:]):
        assert len(louder) > len(quieter)
        assert rms(louder) > rms(quieter)


def test_the_wake_level_one_is_longer_and_louder_than_the_alarm():
    wake, alarm = samples(chime.WAKE), samples(chime.ALARM)

    assert len(wake) > len(alarm)
    assert max(map(abs, wake)) > max(map(abs, alarm))


@pytest.mark.parametrize("level", chime.WAKE_LEVELS)
def test_a_wake_level_grows_louder_burst_by_burst(level):
    loudness = [amplitude for hertz, _, amplitude in chime.SOUNDS[level] if hertz]
    assert loudness == sorted(loudness) and loudness[-1] > loudness[0]

    values = samples(level)
    third = len(values) // 3
    assert max(map(abs, values[:third])) < max(map(abs, values[-third:]))


@pytest.mark.parametrize("level", chime.WAKE_LEVELS)
def test_a_wake_level_never_clips(level):
    ceiling = int(chime.MAX_AMPLITUDE * 32767)

    assert max(map(abs, samples(level))) <= ceiling < 32767
    assert all(amplitude <= chime.MAX_AMPLITUDE for _, _, amplitude in chime.SOUNDS[level])

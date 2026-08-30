from pathlib import Path

import pytest

from homeauto.voice.speaker import Speaker


class FakeSynth:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.said = []

    def say(self, text):
        self.said.append(text)
        path = self.cache_dir / f"{abs(hash(text))}.wav"
        path.write_bytes(b"RIFF")
        return path


class FakeCaster:
    def __init__(self):
        self.played = []
        self.volumes = []
        self.stopped = 0

    def play(self, url):
        self.played.append(url)

    def set_volume(self, percent):
        self.volumes.append(percent)

    def stop(self):
        self.stopped += 1

    def device_name(self):
        return "Nest"


class FakeServer:
    def __init__(self, directory):
        self.directory = directory
        self.started = 0

    def start(self):
        self.started += 1

    def url_for(self, filename):
        return f"http://fake/{filename}"


@pytest.fixture
def speaker(tmp_path):
    synth = FakeSynth(tmp_path)
    caster = FakeCaster()
    server = FakeServer(tmp_path)
    return Speaker(synth=synth, caster=caster, media_server=server), synth, caster, server


def test_say_synthesizes_then_plays_the_served_url(speaker):
    spk, synth, caster, _ = speaker

    spk.say("hola")

    assert synth.said == ["hola"]
    assert len(caster.played) == 1
    assert caster.played[0].startswith("http://fake/")
    assert caster.played[0].endswith(".wav")


def test_the_played_url_matches_the_synthesized_file(speaker):
    spk, _, caster, _ = speaker

    path = spk.say("hola")

    assert caster.played[0] == f"http://fake/{path.name}"


def test_server_is_started_once_even_after_several_phrases(speaker):
    spk, _, _, server = speaker

    spk.say("una")
    spk.say("dos")

    assert server.started == 1


def test_volume_is_delegated(speaker):
    spk, _, caster, _ = speaker

    spk.set_volume(40)

    assert caster.volumes == [40]


def test_stop_is_delegated(speaker):
    spk, _, caster, _ = speaker

    spk.stop()

    assert caster.stopped == 1


def test_device_name_is_exposed(speaker):
    spk, _, _, _ = speaker

    assert spk.device_name() == "Nest"

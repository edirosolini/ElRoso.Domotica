import uuid

import pytest

from homeauto.voice.caster import CastError, Caster

DEVICE_UUID = uuid.UUID("d17e8311-d82e-5116-8f58-6292603bbc1b")
OTHER_UUID = uuid.UUID("11111111-2222-3333-4444-555555555555")


class FakeMediaController:
    def __init__(self):
        self.played = []
        self.stopped = 0
        self.blocked = 0

    def play_media(self, url, mime):
        self.played.append((url, mime))

    def block_until_active(self, timeout=None):
        self.blocked += 1

    def stop(self):
        self.stopped += 1


class FakeDevice:
    def __init__(self, device_uuid=DEVICE_UUID, name="Nest"):
        self.cast_info = type("Info", (), {"uuid": device_uuid, "friendly_name": name, "host": "192.168.68.20"})()
        self.media_controller = FakeMediaController()
        self.volumes = []
        self.waited = 0

    def wait(self, timeout=None):
        self.waited += 1

    def set_volume(self, level):
        self.volumes.append(level)


def discovery_of(*devices):
    calls = []

    def discover(timeout=None):
        calls.append(timeout)
        return list(devices)

    discover.calls = calls
    return discover


def test_resolves_the_device_by_uuid():
    wanted = FakeDevice()
    caster = Caster(DEVICE_UUID, discover=discovery_of(FakeDevice(OTHER_UUID, "Otro"), wanted))

    assert caster.device_name() == "Nest"
    assert wanted.waited == 1


def test_unknown_device_is_reported_clearly():
    caster = Caster(DEVICE_UUID, discover=discovery_of(FakeDevice(OTHER_UUID, "Otro")))

    with pytest.raises(CastError, match="No encontré"):
        caster.device_name()


def test_play_sends_url_and_waits_for_the_receiver():
    device = FakeDevice()
    caster = Caster(DEVICE_UUID, discover=discovery_of(device))

    caster.play("http://192.168.68.10:8765/hola.wav")

    assert device.media_controller.played == [("http://192.168.68.10:8765/hola.wav", "audio/wav")]
    assert device.media_controller.blocked == 1


def test_device_is_discovered_once_and_reused():
    device = FakeDevice()
    discover = discovery_of(device)
    caster = Caster(DEVICE_UUID, discover=discover)

    caster.play("http://x/1.wav")
    caster.play("http://x/2.wav")

    assert len(discover.calls) == 1, "no hay que redescubrir en cada mensaje"


def test_volume_is_scaled_from_percent():
    device = FakeDevice()
    caster = Caster(DEVICE_UUID, discover=discovery_of(device))

    caster.set_volume(55)

    assert device.volumes == [pytest.approx(0.55)]


def test_volume_accepts_the_edges():
    device = FakeDevice()
    caster = Caster(DEVICE_UUID, discover=discovery_of(device))

    caster.set_volume(0)
    caster.set_volume(100)

    assert device.volumes == [pytest.approx(0.0), pytest.approx(1.0)]


@pytest.mark.parametrize("bad", [-1, 101, 500])
def test_volume_out_of_range_is_rejected(bad):
    caster = Caster(DEVICE_UUID, discover=discovery_of(FakeDevice()))

    with pytest.raises(CastError, match="entre 0 y 100"):
        caster.set_volume(bad)


def test_stop_stops_playback():
    device = FakeDevice()
    caster = Caster(DEVICE_UUID, discover=discovery_of(device))

    caster.stop()

    assert device.media_controller.stopped == 1

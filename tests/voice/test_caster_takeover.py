"""Playing on a device that is already busy with another app."""

import uuid

import pytest

from homeauto.voice.caster import MEDIA_RECEIVER_APP_ID, CastError, Caster

DEVICE_UUID = uuid.UUID("d17e8311-d82e-5116-8f58-6292603bbc1b")
YOUTUBE_APP_ID = "233637DE"


class FakeMediaController:
    def __init__(self, states, content_id=None):
        self.states = list(states)
        self.status = type(
            "Status", (), {"player_state": "UNKNOWN", "idle_reason": None, "content_id": content_id}
        )()
        self.played = []

    def play_media(self, url, mime):
        self.played.append((url, mime))
        self.status.content_id = url

    def block_until_active(self, timeout=None):
        pass

    def update_status(self):
        if self.states:
            state, reason = self.states.pop(0)
            self.status.player_state = state
            self.status.idle_reason = reason

    def stop(self):
        pass


class FakeDevice:
    def __init__(self, app_id=None, states=(("PLAYING", None),), content_id=None):
        self.cast_info = type(
            "Info", (), {"uuid": DEVICE_UUID, "friendly_name": "TV", "host": "192.168.68.25"}
        )()
        self.app_id = app_id
        self.media_controller = FakeMediaController(states, content_id)
        self.quits = 0

    def wait(self, timeout=None):
        pass

    def quit_app(self):
        self.quits += 1
        self.app_id = None

    def set_volume(self, level):
        pass


def caster_for(device):
    return Caster(DEVICE_UUID, discover=lambda timeout=None: [device], settle=0)


def test_a_foreign_app_is_kicked_out_before_playing():
    device = FakeDevice(app_id=YOUTUBE_APP_ID)

    caster_for(device).play("http://x/hola.wav")

    assert device.quits == 1, "con YouTube abierto la orden se la come YouTube"
    assert device.media_controller.played, "y después hay que reproducir igual"


def test_an_idle_device_is_not_disturbed():
    device = FakeDevice(app_id=None)

    caster_for(device).play("http://x/hola.wav")

    assert device.quits == 0


def test_our_own_receiver_is_not_kicked_out():
    device = FakeDevice(app_id=MEDIA_RECEIVER_APP_ID)

    caster_for(device).play("http://x/hola.wav")

    assert device.quits == 0, "relanzarlo corta el audio anterior sin necesidad"


def test_playing_is_confirmed_before_reporting_success():
    device = FakeDevice(states=[("BUFFERING", None), ("PLAYING", None)])

    caster_for(device).play("http://x/hola.wav")  # no explota


def test_a_very_short_clip_that_already_finished_counts_as_played():
    device = FakeDevice(states=[("IDLE", "FINISHED")])

    caster_for(device).play("http://x/hola.wav")


def test_silence_is_reported_instead_of_pretending_it_played():
    device = FakeDevice(states=[("UNKNOWN", None)] * 40)

    with pytest.raises(CastError, match="no empezó a sonar"):
        caster_for(device).play("http://x/hola.wav", timeout=0.2)


def test_a_playback_error_is_surfaced():
    device = FakeDevice(states=[("IDLE", "ERROR")])

    with pytest.raises(CastError, match="rechazó"):
        caster_for(device).play("http://x/hola.wav")


def test_a_stale_playing_state_from_the_previous_clip_is_not_enough():
    """El equipo puede seguir informando el audio anterior por unos instantes.

    Si se acepta ese PLAYING, se reporta que sonó algo que todavía no cargó.
    """
    device = FakeDevice(states=[("PLAYING", None)] * 40, content_id="http://x/anterior.wav")
    device.media_controller.play_media = lambda url, mime: device.media_controller.played.append((url, mime))

    with pytest.raises(CastError, match="no empezó a sonar"):
        caster_for(device).play("http://x/nuevo.wav", timeout=0.2)


def test_playing_the_clip_we_asked_for_is_accepted():
    device = FakeDevice(states=[("PLAYING", None)])

    caster_for(device).play("http://x/hola.wav")

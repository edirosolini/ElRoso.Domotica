"""La pantalla de la casa en una tele, por DashCast, y su vuelta después de un anuncio."""

import uuid

import pytest

from homeauto.voice.caster import APP_DASHCAST, MEDIA_RECEIVER_APP_ID, CastError, Caster

DEVICE_UUID = uuid.UUID("d17e8311-d82e-5116-8f58-6292603bbc1b")
YOUTUBE_APP_ID = "233637DE"
KIOSK = "http://casa:8099/pantalla?ver=1"


class FakeStatus:
    def __init__(self):
        self.player_state = "UNKNOWN"
        self.idle_reason = None
        self.content_id = None


class FakeMediaController:
    """Carga el clip, lo reporta y lo termina tras unos sondeos, como el receptor real."""

    def __init__(self, device, finishes_after=3):
        self.device = device
        self.status = FakeStatus()
        self.finishes_after = finishes_after
        self.polls = 0

    def play_media(self, url, mime):
        self.device.log.append(("play", url))
        self.device.app_id = MEDIA_RECEIVER_APP_ID
        self.status.content_id = url
        self.status.player_state = "PLAYING"
        self.polls = 0

    def block_until_active(self, timeout=None):
        pass

    def update_status(self):
        self.polls += 1
        if self.status.content_id and self.polls > self.finishes_after:
            if self.status.player_state != "IDLE":
                self.device.log.append(("finished", self.status.content_id))
            self.status.player_state = "IDLE"
            self.status.idle_reason = "FINISHED"

    def stop(self):
        pass


class FakeDashCast:
    """El controlador de DashCast: al cargar una URL deja la app abierta en el equipo."""

    def __init__(self, fail=None):
        self.device = None
        self.fail = fail

    def load_url(self, url, *, force=False, reload_seconds=0, callback_function=None):
        if self.fail:
            raise self.fail
        self.device.log.append(("show", url, force))
        self.device.app_id = APP_DASHCAST


class FakeDevice:
    def __init__(self, app_id=None, volume=0.95):
        self.cast_info = type(
            "Info", (), {"uuid": DEVICE_UUID, "friendly_name": "TV", "host": "192.168.68.20"}
        )()
        self.app_id = app_id
        self.status = type("Status", (), {"volume_level": volume})()
        self.media_controller = FakeMediaController(self)
        self.log = []
        self.handlers = []

    def wait(self, timeout=None):
        pass

    def register_handler(self, handler):
        handler.device = self
        self.handlers.append(handler)

    def quit_app(self):
        self.log.append(("quit", self.app_id))
        self.app_id = None

    def set_volume(self, level):
        self.log.append(("volume", level))


def caster_for(device, screen=None, dashcast=FakeDashCast):
    return Caster(
        DEVICE_UUID,
        discover=lambda timeout=None: [device],
        settle=0,
        locate=lambda _uuid: None,
        dashcast=dashcast,
        screen=screen,
    )


def test_show_opens_dashcast_forcing_the_page_out_of_the_iframe():
    device = FakeDevice()

    caster_for(device).show(KIOSK)

    assert device.log == [("show", KIOSK, True)]
    assert len(device.handlers) == 1
    assert device.app_id == APP_DASHCAST


def test_showing_on_a_tv_that_is_not_there_fails_as_a_cast_error():
    caster = Caster(
        DEVICE_UUID, discover=lambda timeout=None: [], locate=lambda _uuid: None,
        dashcast=FakeDashCast,
    )

    with pytest.raises(CastError):
        caster.show(KIOSK)


def test_showing_tells_whether_dashcast_is_open():
    assert caster_for(FakeDevice(app_id=APP_DASHCAST)).showing() is True
    assert caster_for(FakeDevice(app_id=YOUTUBE_APP_ID)).showing() is False
    assert caster_for(FakeDevice(app_id=None)).showing() is False


def test_hide_closes_dashcast():
    device = FakeDevice(app_id=APP_DASHCAST)

    assert caster_for(device).hide() is True

    assert device.log == [("quit", APP_DASHCAST)]
    assert device.app_id is None


def test_hide_does_not_close_an_app_someone_else_opened():
    device = FakeDevice(app_id=YOUTUBE_APP_ID)

    assert caster_for(device).hide() is False

    assert device.log == []
    assert device.app_id == YOUTUBE_APP_ID


def test_after_an_announcement_the_screen_comes_back_once_the_clip_ends():
    device = FakeDevice(app_id=APP_DASHCAST)
    asked = []

    def screen():
        asked.append(True)
        return KIOSK

    caster_for(device, screen=screen).play("http://casa/hola.wav")

    assert device.log == [
        ("quit", APP_DASHCAST),
        ("play", "http://casa/hola.wav"),
        ("finished", "http://casa/hola.wav"),
        ("show", KIOSK, True),
    ]
    assert asked == [True]


def test_the_screen_comes_back_with_the_url_of_the_moment():
    device = FakeDevice(app_id=APP_DASHCAST)
    alarm = "http://casa:8099/alarma?job=17"

    caster_for(device, screen=lambda: alarm).play("http://casa/arriba.wav")

    assert device.log[-1] == ("show", alarm, True)


def test_the_screen_comes_back_also_when_the_volume_was_raised():
    device = FakeDevice(app_id=APP_DASHCAST, volume=0.2)

    caster_for(device, screen=lambda: KIOSK).play("http://casa/hola.wav", min_volume=60)

    shown = device.log.index(("show", KIOSK, True))
    assert ("volume", 0.2) in device.log[:shown], "primero devuelve el volumen"


def test_without_a_url_the_screen_stays_closed():
    device = FakeDevice(app_id=APP_DASHCAST)

    caster_for(device, screen=lambda: None).play("http://casa/hola.wav")

    assert not [entry for entry in device.log if entry[0] == "show"]


def test_a_screen_that_cannot_come_back_does_not_fail_the_announcement():
    device = FakeDevice(app_id=APP_DASHCAST)

    caster_for(
        device, screen=lambda: KIOSK, dashcast=lambda: FakeDashCast(fail=OSError("se cortó"))
    ).play("http://casa/hola.wav")

    assert ("play", "http://casa/hola.wav") in device.log


def test_a_url_that_cannot_be_read_does_not_fail_the_announcement():
    device = FakeDevice(app_id=APP_DASHCAST)

    def broken():
        raise RuntimeError("sin base")

    caster_for(device, screen=broken).play("http://casa/hola.wav")

    assert ("play", "http://casa/hola.wav") in device.log


@pytest.mark.parametrize("app_id", [None, YOUTUBE_APP_ID, MEDIA_RECEIVER_APP_ID])
def test_only_a_screen_that_was_open_comes_back(app_id):
    device = FakeDevice(app_id=app_id)

    caster_for(device, screen=lambda: KIOSK).play("http://casa/hola.wav")

    assert not [entry for entry in device.log if entry[0] == "show"]


def test_the_speaker_hands_the_screen_to_its_caster():
    from homeauto.voice.speaker import Speaker

    device = FakeDevice(app_id=None)
    speaker = Speaker(synth=None, caster=caster_for(device), media_server=None)

    speaker.show(KIOSK)
    assert speaker.showing() is True
    assert speaker.hide() is True
    assert speaker.showing() is False

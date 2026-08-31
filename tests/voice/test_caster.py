import uuid

import pytest

from homeauto.voice.caster import CastError, Caster

DEVICE_UUID = uuid.UUID("d17e8311-d82e-5116-8f58-6292603bbc1b")
OTHER_UUID = uuid.UUID("11111111-2222-3333-4444-555555555555")


class FakeStatus:
    def __init__(self):
        self.player_state = "UNKNOWN"
        self.idle_reason = None
        self.content_id = None


class FakeMediaController:
    """Se comporta como el receptor real: recién reporta el clip al cargarlo.

    🔴 Antes el doble no traía `content_id`, o sea que fingía el estado exacto
    en el que el caster daba por bueno un audio que nunca sonó.
    """

    def __init__(self, loads=True, finishes_after=2):
        self.played = []
        self.stopped = 0
        self.blocked = 0
        self.loads = loads
        self.finishes_after = finishes_after
        self.polls = 0
        self.status = FakeStatus()

    def update_status(self):
        """Un clip real termina. Un doble que se queda en PLAYING para siempre
        hace esperar al test lo mismo que esperaría a un equipo colgado."""
        self.polls += 1
        if self.status.content_id and self.polls > self.finishes_after:
            self.status.player_state = "IDLE"
            self.status.idle_reason = "FINISHED"

    def play_media(self, url, mime):
        self.played.append((url, mime))
        if self.loads:
            self.status.content_id = url
            self.status.player_state = "PLAYING"

    def block_until_active(self, timeout=None):
        self.blocked += 1

    def stop(self):
        self.stopped += 1


class FakeDevice:
    def __init__(self, device_uuid=DEVICE_UUID, name="Nest", volume=0.30, loads=True):
        self.cast_info = type("Info", (), {"uuid": device_uuid, "friendly_name": name, "host": "192.168.68.20"})()
        self.media_controller = FakeMediaController(loads=loads)
        self.volumes = []
        self.waited = 0
        self.app_id = None
        self.status = type("Status", (), {"volume_level": volume, "volume_muted": False})()

    def quit_app(self):
        self.app_id = None

    def wait(self, timeout=None):
        self.waited += 1

    def set_volume(self, level):
        self.volumes.append(level)
        self.status.volume_level = level


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


# --- confirmar que sonó de verdad ------------------------------------------


def test_a_device_that_never_loads_the_clip_is_a_failure():
    """🔴 Un equipo que no reporta nuestro audio no lo está reproduciendo.

    Antes `content_id` vacío contaba como "cargado": el caster daba por bueno
    un anuncio que nunca salió, y arriba se informaba que la casa fue avisada.
    """
    device = FakeDevice(loads=False)
    caster = Caster(DEVICE_UUID, discover=discovery_of(device), discovery_timeout=0)

    with pytest.raises(CastError, match="no empezó a sonar"):
        caster.play("http://192.168.68.10:8765/a.wav", timeout=0.3)


def test_buffering_without_saying_what_is_loaded_is_not_enough():
    """El caso real: receptor recién lanzado, dice BUFFERING y todavía no el clip.

    Es como se veía la caída del VPS que no se escuchó: el equipo reportaba
    algo, el caster lo daba por sonando y el audio nunca se cargó.
    """
    device = FakeDevice(loads=False)
    device.media_controller.status.player_state = "BUFFERING"
    caster = Caster(DEVICE_UUID, discover=discovery_of(device), discovery_timeout=0)

    with pytest.raises(CastError, match="no empezó a sonar"):
        caster.play("http://192.168.68.10:8765/a.wav", timeout=0.3)


def test_the_clip_of_someone_else_does_not_count():
    device = FakeDevice()
    device.media_controller.status.content_id = "http://192.168.68.10:8765/anterior.wav"
    device.media_controller.loads = False
    device.media_controller.status.player_state = "PLAYING"
    caster = Caster(DEVICE_UUID, discover=discovery_of(device), discovery_timeout=0)

    with pytest.raises(CastError, match="no empezó a sonar"):
        caster.play("http://192.168.68.10:8765/nuevo.wav", timeout=0.3)


def test_a_clip_that_ended_before_the_first_poll_still_counts():
    device = FakeDevice()
    caster = Caster(DEVICE_UUID, discover=discovery_of(device), discovery_timeout=0)
    url = "http://192.168.68.10:8765/corto.wav"

    def play_media(played_url, mime):
        device.media_controller.played.append((played_url, mime))
        device.media_controller.status.content_id = played_url
        device.media_controller.status.player_state = "IDLE"
        device.media_controller.status.idle_reason = "FINISHED"

    device.media_controller.play_media = play_media

    caster.play(url, timeout=0.3)


# --- volumen mínimo para lo urgente ----------------------------------------


def test_an_announcement_raises_a_low_volume():
    device = FakeDevice(volume=0.30)
    caster = Caster(DEVICE_UUID, discover=discovery_of(device), discovery_timeout=0)

    caster.play("http://192.168.68.10:8765/a.wav", timeout=0.3, min_volume=60, expected_seconds=0)

    assert device.volumes == [0.6, 0.30], "sube, y deja el volumen como estaba"


def test_a_volume_already_high_enough_is_left_alone():
    device = FakeDevice(volume=0.80)
    caster = Caster(DEVICE_UUID, discover=discovery_of(device), discovery_timeout=0)

    caster.play("http://192.168.68.10:8765/a.wav", timeout=0.3, min_volume=60, expected_seconds=0)

    assert device.volumes == []


def test_the_volume_comes_back_even_if_the_audio_fails():
    device = FakeDevice(volume=0.30, loads=False)
    caster = Caster(DEVICE_UUID, discover=discovery_of(device), discovery_timeout=0)

    with pytest.raises(CastError):
        caster.play("http://192.168.68.10:8765/a.wav", timeout=0.3, min_volume=60, expected_seconds=0)

    assert device.volumes[-1] == 0.30, "un audio que falla no puede dejar la casa a todo volumen"


def test_without_a_floor_the_volume_is_never_touched():
    device = FakeDevice(volume=0.05)
    caster = Caster(DEVICE_UUID, discover=discovery_of(device), discovery_timeout=0)

    caster.play("http://192.168.68.10:8765/a.wav", timeout=0.3)

    assert device.volumes == []


def test_the_volume_waits_for_a_long_clip_to_end():
    """🔴 El resumen de la mañana dura más que el timeout de arranque.

    Devolver el volumen a mitad de frase es justo lo que el piso venía a
    evitar, así que esperar el final tiene su propio límite.
    """
    device = FakeDevice(volume=0.30)
    polls = []

    def update_status():
        polls.append(1)
        if len(polls) >= 4:  # el clip recién termina en el cuarto sondeo
            device.media_controller.status.player_state = "IDLE"
            device.media_controller.status.idle_reason = "FINISHED"

    device.media_controller.update_status = update_status
    caster = Caster(DEVICE_UUID, discover=discovery_of(device), discovery_timeout=0)

    caster.play(
        "http://192.168.68.10:8765/largo.wav", timeout=5, min_volume=60, expected_seconds=1
    )

    assert len(polls) >= 4, "no esperó a que terminara"
    assert device.volumes == [0.6, 0.30]


def test_the_wait_for_the_end_follows_the_length_of_the_audio():
    """Un clip largo espera más; uno corto no cuelga el hilo dos minutos."""
    caster = Caster(DEVICE_UUID, discover=discovery_of(FakeDevice()))

    assert caster._finish_deadline(2) == 2 + 5
    assert caster._finish_deadline(40) == 40 + 5
    # Sin duración legible queda el tope, no un número inventado.
    assert caster._finish_deadline(None) == 120
    # Y el tope manda incluso si el wav dice cualquier cosa.
    assert caster._finish_deadline(9999) == 120

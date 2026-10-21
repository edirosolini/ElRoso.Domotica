"""Lo que el CT le diría a una tele por Cast va a su app, con Cast de respaldo."""

import threading
import time
from datetime import datetime, timedelta

import pytest

from homeauto.tele import STALE, TeleLink, TeleStore
from homeauto.voice.caster import FINISH_MARGIN, FINISH_TIMEOUT
from homeauto.voice.tele import ACK_TIMEOUT, APP_WAKE_MARGIN, TeleCaster

NOW = datetime(2026, 10, 21, 12, 0)
URL = "http://192.0.2.10:8765/a.wav"


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


class FakeCaster:
    """El Caster de un equipo: anota lo que se le pidió."""

    def __init__(self):
        self.calls = []
        self.screen = "la página de siempre"
        self.hide_result = True
        self.hide_error = None

    def play(self, url, min_volume=None, expected_seconds=None):
        self.calls.append(("play", url, min_volume, expected_seconds))

    def show(self, url):
        self.calls.append(("show", url))

    def stop(self):
        self.calls.append(("stop",))

    def set_volume(self, percent):
        self.calls.append(("set_volume", percent))

    def turn_off(self):
        self.calls.append(("turn_off",))

    def hide(self):
        self.calls.append(("hide",))
        if self.hide_error is not None:
            raise self.hide_error
        return self.hide_result

    def showing(self):
        return False

    def device_name(self):
        return "Comedor TV"


class App:
    """La app de la tele en un hilo: lee el buzón y contesta cada orden con `states`."""

    def __init__(self, link, states=("received", "done")):
        self.link = link
        self.states = states
        self.seen = []
        self._quit = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._quit.set()
        self._thread.join(timeout=2)

    def _run(self):
        while not self._quit.is_set():
            for order in self.link.orders("comedor"):
                self.seen.append(order)
                for state in self.states:
                    self.link.ack("comedor", order["seq"], state)
            time.sleep(0.001)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def link(tmp_path, clock):
    link = TeleLink(TeleStore(tmp_path / "jobs.db"), clock=clock)
    link.hello("comedor", "1.0", 1, ["play", "show"], "")
    return link


@pytest.fixture
def cast():
    return FakeCaster()


def tele(link, cast, **timeouts):
    return TeleCaster("comedor", cast, link, **timeouts)


def test_the_wait_for_the_app_is_ten_seconds():
    assert ACK_TIMEOUT == 10


def test_a_live_app_that_confirms_plays_it_and_cast_is_not_used(link, cast):
    with App(link) as app:
        tele(link, cast).play(URL, min_volume=90, expected_seconds=3.0)

    assert cast.calls == []
    assert [(o["kind"], o["url"], o["min_volume"], o["seconds"]) for o in app.seen] == [
        ("play", URL, 90, 3.0)
    ]


def test_the_app_gets_thirteen_seconds_to_wake_the_tele():
    assert APP_WAKE_MARGIN == 13


@pytest.mark.parametrize(
    "seconds, deadline",
    [
        (3.0, 3.0 + FINISH_MARGIN + APP_WAKE_MARGIN),
        (None, FINISH_TIMEOUT + APP_WAKE_MARGIN),
        (FINISH_TIMEOUT, FINISH_TIMEOUT + APP_WAKE_MARGIN),
    ],
)
def test_the_wait_for_done_adds_the_wake_of_the_tele(tmp_path, clock, cast, seconds, deadline):
    class Recording(TeleLink):
        def wait(self, alias, seq, states, timeout):
            self.waits.append((tuple(states), timeout))
            return "received" if len(self.waits) == 1 else "done"

    link = Recording(TeleStore(tmp_path / "jobs.db"), clock=clock)
    link.waits = []
    link.hello("comedor", "1.0", 1, ["play"], "")

    tele(link, cast).play(URL, expected_seconds=seconds)

    assert link.waits == [(("received",), ACK_TIMEOUT), (("done",), deadline)]
    assert cast.calls == []


def test_a_stale_app_goes_straight_to_cast(link, cast, clock):
    clock.now += STALE

    tele(link, cast).play(URL, min_volume=90, expected_seconds=3.0)

    assert cast.calls == [("play", URL, 90, 3.0)]
    assert link.orders("comedor") == []


def test_an_app_without_play_goes_to_cast(tmp_path, clock, cast):
    link = TeleLink(TeleStore(tmp_path / "jobs.db"), clock=clock)
    link.hello("comedor", "1.0", 1, ["show", "overlay"], "")

    tele(link, cast).play(URL)

    assert cast.calls == [("play", URL, None, None)]
    assert link.orders("comedor") == []


def test_without_an_ack_the_order_is_dropped_and_cast_plays_once(link, cast):
    tele(link, cast, ack_timeout=0.01).play(URL, min_volume=60, expected_seconds=2.0)

    assert cast.calls == [("play", URL, 60, 2.0)]
    assert link.orders("comedor") == [], "la orden anulada no se entrega"


def test_a_late_ack_after_falling_back_does_not_play_it_again(tmp_path, clock, cast):
    class Recording(TeleLink):
        def send(self, alias, kind, **fields):
            self.sent = super().send(alias, kind, **fields)
            return self.sent

    link = Recording(TeleStore(tmp_path / "jobs.db"), clock=clock)
    link.hello("comedor", "1.0", 1, ["play"], "")
    tele(link, cast, ack_timeout=0.01).play(URL)
    seq = link.sent

    assert link.ack("comedor", seq, "received") is False
    assert link.ack("comedor", seq, "done") is False
    assert cast.calls == [("play", URL, None, None)]


def test_received_but_never_done_falls_back_to_cast_once(link, cast):
    with App(link, states=("received",)):
        tele(link, cast, finish_timeout=0.01, wake_margin=0).play(URL, expected_seconds=0.0)

    assert cast.calls == [("play", URL, None, 0.0)]


@pytest.mark.parametrize("states", [("failed",), ("received", "failed")])
def test_a_failed_order_goes_to_cast_once(link, cast, states):
    with App(link, states=states):
        tele(link, cast).play(URL, min_volume=90, expected_seconds=3.0)

    assert cast.calls == [("play", URL, 90, 3.0)]


def test_a_play_stopped_while_waiting_does_not_go_to_cast(link, cast):
    caster = tele(link, cast)
    threading.Timer(0.01, caster.stop).start()

    caster.play(URL)

    assert cast.calls == []
    assert [order["kind"] for order in link.orders("comedor")] == ["stop"]


def test_show_goes_to_a_live_app_with_show(link, cast):
    with App(link, states=("received",)) as app:
        tele(link, cast).show("http://casa/alarma?job=7")

    assert cast.calls == []
    assert [(o["kind"], o["url"]) for o in app.seen] == [("show", "http://casa/alarma?job=7")]


def test_show_without_the_cap_or_alive_goes_to_cast(tmp_path, clock, cast):
    link = TeleLink(TeleStore(tmp_path / "jobs.db"), clock=clock)
    link.hello("comedor", "1.0", 1, ["play"], "")

    tele(link, cast).show("http://casa/pantalla?ver=1")
    link.hello("comedor", "1.0", 1, ["show"], "")
    clock.now += STALE
    tele(link, cast).show("http://casa/pantalla?ver=1")

    assert cast.calls == [("show", "http://casa/pantalla?ver=1")] * 2
    assert link.orders("comedor") == []


def test_show_without_an_ack_falls_back_to_cast(link, cast):
    tele(link, cast, ack_timeout=0.01).show("http://casa/alarma?job=7")

    assert cast.calls == [("show", "http://casa/alarma?job=7")]
    assert link.orders("comedor") == []


def test_stop_goes_to_a_live_app(link, cast):
    tele(link, cast).stop()

    assert cast.calls == []
    assert [order["kind"] for order in link.orders("comedor")] == ["stop"]


def test_stop_without_the_app_goes_to_cast(link, cast, clock):
    clock.now += STALE

    tele(link, cast).stop()

    assert cast.calls == [("stop",)]
    assert link.orders("comedor") == []


def test_after_falling_back_stop_also_reaches_cast(link, cast):
    caster = tele(link, cast, ack_timeout=0.01)
    caster.play(URL)

    caster.stop()

    assert cast.calls == [("play", URL, None, None), ("stop",)]
    assert [order["kind"] for order in link.orders("comedor")] == ["stop"]


def test_volume_and_turning_off_stay_on_cast(link, cast):
    caster = tele(link, cast)

    caster.set_volume(40)
    caster.turn_off()

    assert cast.calls == [("set_volume", 40), ("turn_off",)]
    assert link.orders("comedor") == []


def test_the_rest_is_the_caster_of_always(link, cast):
    caster = tele(link, cast)

    assert caster.showing() is False
    assert caster.device_name() == "Comedor TV"
    assert caster.screen == "la página de siempre"
    assert link.orders("comedor") == []


def test_hide_sends_a_live_app_back_and_also_closes_dashcast(link, cast):
    cast.hide_result = False
    with App(link, states=("received",)) as app:
        assert tele(link, cast).hide() is True

    assert [o["kind"] for o in app.seen] == ["hide"]
    assert cast.calls == [("hide",)]


def test_hide_confirmed_by_the_app_survives_a_cast_failure(link, cast):
    cast.hide_error = OSError("sin cast")
    with App(link, states=("received",)):
        assert tele(link, cast).hide() is True


def test_hide_without_an_ack_is_dropped_and_answers_what_cast_did(link, cast):
    cast.hide_result = False

    assert tele(link, cast, ack_timeout=0.01).hide() is False
    assert cast.calls == [("hide",)]
    assert link.orders("comedor") == []


def test_hide_without_a_live_app_with_show_goes_only_to_cast(tmp_path, clock, cast):
    link = TeleLink(TeleStore(tmp_path / "jobs.db"), clock=clock)
    link.hello("comedor", "1.0", 1, ["play"], "")

    assert tele(link, cast).hide() is True
    link.hello("comedor", "1.0", 1, ["show"], "")
    clock.now += STALE
    cast.hide_error = OSError("sin cast")
    with pytest.raises(OSError):
        tele(link, cast).hide()

    assert link.orders("comedor") == []


def test_the_speaker_says_it_through_the_app(link, cast, tmp_path):
    import wave

    from homeauto.voice.speaker import Speaker

    class Synth:
        def say(self, text, chime=False):
            path = tmp_path / "frase.wav"
            with wave.open(str(path), "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(22050)
                target.writeframes(b"\x00" * 2 * 22050)
            return path

    class Media:
        def start(self):
            pass

        def url_for(self, name):
            return f"http://192.0.2.10:8765/{name}"

    with App(link) as app:
        Speaker(synth=Synth(), caster=tele(link, cast), media_server=Media()).say("arriba")

    assert cast.calls == []
    assert [(o["url"], o["min_volume"], o["seconds"]) for o in app.seen] == [
        ("http://192.0.2.10:8765/frase.wav", 60, 1.0)
    ]

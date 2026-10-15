"""/pantalla: el kiosco de la casa en una tele, y cómo sacarlo."""

from datetime import datetime, time, timedelta

import pytest

from homeauto.bot.commands import HELP, Commands, with_actions
from homeauto.quiet import AwayStore, Hush, HushStore, QuietHours
from homeauto.screen import ScreenPages, ScreenStore, Screens
from homeauto.voice.caster import CastError
from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
STRANGER = 99
NOON = datetime(2026, 10, 15, 12, 0)
KIOSK = "http://casa:8099/pantalla?ver=1"


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)


class FakeTV(FakeSpeaker):
    """Una tele que muestra una página y la cierra solo si sigue abierta."""

    def __init__(self, name):
        super().__init__(name)
        self.page = None

    def show(self, url):
        if self.fail:
            raise self.fail
        self.page = url

    def showing(self):
        return self.page is not None

    def hide(self):
        if self.fail:
            raise self.fail
        if self.page is None:
            return False
        self.page = None
        return True


@pytest.fixture
def house(tmp_path):
    path = tmp_path / "jobs.db"
    tvs = {name: FakeTV(name) for name in ("parlante", "comedor", "recamara")}
    hush = Hush(QuietHours(time(0, 0), time(0, 0)), HushStore(path), clock=lambda: NOON,
                away=AwayStore(path))
    registry = StubRegistry(**tvs)
    screens = Screens(
        speakers=registry,
        devices=("comedor", "recamara", "habitacion"),
        pages=ScreenPages(
            base=lambda: "http://casa:8099", store=ScreenStore(path), quiet=hush,
            clock=lambda: NOON,
        ),
        timer=FakeTimer(),
        fallback="parlante",
    )

    def build(with_screens=True):
        return Commands(
            config=make_config(allowed=[OWNER]),
            speakers=registry,
            quiet=hush,
            screens=screens if with_screens else None,
            clock=lambda: NOON,
        )

    return type("House", (), {"tvs": tvs, "hush": hush, "build": staticmethod(build)})


def test_without_the_api_there_is_no_screen(house):
    assert house.build(with_screens=False).screen(OWNER, "") == "La pantalla no está prendida."


def test_without_argument_it_shows_in_the_dining_room(house):
    reply = with_actions(house.build().screen, OWNER, "")

    assert house.tvs["comedor"].page == KIOSK
    assert "comedor" in reply.text
    assert reply.actions == (("Apagar pantalla", "pantalla apagar en comedor"),)


def test_another_tv_is_named_as_always(house):
    reply = with_actions(house.build().screen, OWNER, "en recamara")

    assert house.tvs["recamara"].page == KIOSK
    assert house.tvs["comedor"].page is None
    assert reply.actions == (("Apagar pantalla", "pantalla apagar en recamara"),)


def test_the_button_fits_in_telegram():
    assert len("pantalla apagar en habitacion".encode("utf-8")) <= 64


def test_apagar_closes_the_screen(house):
    house.tvs["comedor"].page = KIOSK

    reply = house.build().screen(OWNER, "apagar")

    assert house.tvs["comedor"].page is None
    assert reply == "Apagué la pantalla del comedor."


def test_apagar_names_another_tv(house):
    house.tvs["recamara"].page = KIOSK

    reply = house.build().screen(OWNER, "apagar en recamara")

    assert house.tvs["recamara"].page is None
    assert reply == "Apagué la pantalla de la recamara."


def test_apagar_when_it_was_not_on_says_so(house):
    assert house.build().screen(OWNER, "apagar") == "La pantalla del comedor no estaba prendida."


def test_the_button_turns_it_off(house):
    commands = house.build()
    commands.screen(OWNER, "")

    reply = commands.press(OWNER, "pantalla apagar en comedor")

    assert reply == "Apagué la pantalla del comedor."
    assert house.tvs["comedor"].page is None


def test_a_tv_that_is_off_is_asked_to_be_turned_on(house):
    house.tvs["comedor"].fail = CastError("No encontré el dispositivo")

    reply = house.build().screen(OWNER, "")

    assert reply == "No veo la tele del comedor: prendela y probá de nuevo."


def test_on_vacation_the_tv_is_not_turned_on(house):
    house.hush.start_away(NOON + timedelta(days=3))

    reply = house.build().screen(OWNER, "")

    assert reply == "De vacaciones: no prendo la tele."
    assert house.tvs["comedor"].page is None


def test_on_vacation_the_screen_can_still_be_turned_off(house):
    house.tvs["comedor"].page = KIOSK
    house.hush.start_away(NOON + timedelta(days=3))

    assert house.build().screen(OWNER, "apagar") == "Apagué la pantalla del comedor."


def test_the_quiet_hours_do_not_stop_it(house):
    house.hush.hours = QuietHours(time(0, 0), time(23, 59))

    house.build().screen(OWNER, "")

    assert house.tvs["comedor"].page == KIOSK


def test_the_speaker_has_no_screen(house):
    reply = house.build().screen(OWNER, "en parlante")

    assert reply == "El parlante no tiene pantalla."
    assert house.tvs["parlante"].page is None


def test_something_else_after_the_tv_is_explained(house):
    reply = house.build().screen(OWNER, "en recamara bien grande")

    assert "/pantalla" in reply
    assert house.tvs["recamara"].page is None


def test_a_stranger_gets_the_door(house):
    reply = house.build().screen(STRANGER, "")

    assert str(STRANGER) in reply
    assert house.tvs["comedor"].page is None


def test_it_is_in_the_help_and_reachable_without_slash(house):
    assert "/pantalla" in HELP
    assert "pantalla" in house.build()._dispatch()


def test_it_is_registered_but_not_in_the_menu():
    from homeauto.main import ALL_COMMANDS, COMMAND_MENU

    assert "pantalla" in ALL_COMMANDS
    assert "pantalla" not in {name for name, _ in COMMAND_MENU}
    assert len(COMMAND_MENU) == 10

"""La vista de alarma en la tele: se prende al sonar, vuelve al kiosco y se cierra sola."""

from datetime import datetime, time, timedelta

import pytest

from homeauto.quiet import AwayStore, Hush, HushStore, QuietHours
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.ringing import RingingStore
from homeauto.schedule.store import ALARM, REMINDER, Job, Store
from homeauto.screen import OFF_DELAY, ScreenPages, ScreenStore, Screens
from homeauto.voice.caster import CastError
from tests.conftest import StubRegistry

OWNER = 42
NOW = datetime(2026, 10, 15, 7, 0)
BASE = "http://casa:8099"
KIOSK = f"{BASE}/pantalla?ver=1"
TVS = ("comedor", "recamara", "habitacion")


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def fire(self, key):
        _, action = self.armed.pop(key)
        action()


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class FakeTV:
    """Una tele: dice, muestra una página y la cierra solo si sigue siendo la nuestra."""

    def __init__(self, log, name, fail=None):
        self.log = log
        self.name = name
        self.fail = fail
        self.page = None
        self.foreign = False

    def say(self, text, chime=False, min_volume=None):
        self.log.append(("say", self.name, text))

    def show(self, url):
        if self.fail:
            raise self.fail
        self.page = url
        self.foreign = False
        self.log.append(("show", self.name, url))

    def showing(self):
        return self.page is not None and not self.foreign

    def hide(self):
        if not self.showing():
            return False
        self.page = None
        self.log.append(("hide", self.name))
        return True

    def stop(self):
        pass


@pytest.fixture
def house(tmp_path):
    path = tmp_path / "jobs.db"
    log = []
    tvs = {name: FakeTV(log, name) for name in ("parlante",) + TVS}
    clock = Clock(NOW)
    timer = FakeTimer()
    hush = Hush(QuietHours(time(0, 0), time(0, 0)), HushStore(path), clock=clock, away=AwayStore(path))

    def build(fallback="parlante"):
        return Screens(
            speakers=StubRegistry(**tvs),
            devices=TVS,
            pages=ScreenPages(base=lambda: BASE, store=ScreenStore(path), quiet=hush, clock=clock),
            timer=timer,
            fallback=fallback,
        )

    return type(
        "House", (), {"path": path, "log": log, "tvs": tvs, "clock": clock, "timer": timer,
                      "hush": hush, "build": staticmethod(build)}
    )


def alarm(job_id=17, device="recamara", kind=ALARM):
    return Job(id=job_id, chat_id=OWNER, when=NOW, message="arriba", device=device, kind=kind)


def alarm_url(job_id=17):
    return f"{BASE}/alarma?job={job_id}"


# --- cuándo se prende ---


def test_an_alarm_on_a_tv_shows_the_alarm_view_there(house):
    screens = house.build()

    screens.ring(alarm())
    screens.light(17)

    assert house.log == [("show", "recamara", alarm_url())]


def test_the_speaker_has_no_screen(house):
    screens = house.build()

    screens.ring(alarm(device="parlante"))
    screens.light(17)

    assert house.log == []


def test_an_alarm_on_two_tvs_shows_on_both(house):
    screens = house.build()

    screens.ring(alarm(device="recamara,parlante,comedor"))
    screens.light(17)

    assert sorted(entry[1] for entry in house.log) == ["comedor", "recamara"]


def test_a_reminder_does_not_turn_the_tv_on(house):
    screens = house.build()

    screens.ring(alarm(kind=REMINDER))
    screens.light(17)

    assert house.log == []


def test_an_alarm_without_a_device_uses_the_fallback(house):
    screens = house.build(fallback="comedor")

    screens.ring(alarm(device=None))
    screens.light(17)

    assert house.log == [("show", "comedor", alarm_url())]


def test_in_the_quiet_hours_the_tv_stays_off(house, tmp_path):
    house.hush.hours = QuietHours(time(22, 0), time(7, 30))
    screens = house.build()

    screens.ring(alarm())
    screens.light(17)

    assert house.log == []


def test_on_vacation_the_tv_stays_off(house):
    house.hush.start_away(NOW + timedelta(days=3))
    screens = house.build()

    screens.ring(alarm())
    screens.light(17)

    assert house.log == []


def test_a_tv_that_is_off_does_not_break_the_alarm(house):
    house.tvs["recamara"].fail = CastError("No encontré el dispositivo")
    screens = house.build()

    screens.ring(alarm())
    screens.light(17)  # no explota


# --- qué vuelve después de cada clip ---


def test_while_it_rings_the_tv_comes_back_to_the_alarm_view(house):
    screens = house.build()
    screens.ring(alarm())

    assert screens.restore_url("recamara") == alarm_url()
    assert screens.restore_url("comedor") == KIOSK


def test_once_it_stops_the_tv_comes_back_to_the_kiosk(house):
    screens = house.build()
    screens.ring(alarm())

    screens.rang(17)

    assert screens.restore_url("recamara") == KIOSK


def test_in_the_quiet_hours_nothing_comes_back(house):
    house.hush.hours = QuietHours(time(22, 0), time(7, 30))
    screens = house.build()

    assert screens.restore_url("comedor") is None


def test_on_vacation_nothing_comes_back(house):
    house.hush.start_away(NOW + timedelta(days=3))
    screens = house.build()

    assert screens.restore_url("comedor") is None


# --- cuándo se cierra ---


def test_a_quarter_of_an_hour_after_it_stops_dashcast_is_closed(house):
    screens = house.build()
    screens.ring(alarm())
    screens.light(17)

    screens.rang(17)

    when, _ = house.timer.armed["screen-off:recamara"]
    assert when == NOW + OFF_DELAY == NOW + timedelta(minutes=15)
    house.timer.fire("screen-off:recamara")
    assert house.log[-1] == ("hide", "recamara")
    assert screens.restore_url("recamara") == KIOSK


def test_an_app_someone_else_opened_in_between_is_not_closed(house):
    screens = house.build()
    screens.ring(alarm())
    screens.light(17)
    screens.rang(17)
    house.tvs["recamara"].foreign = True

    house.timer.fire("screen-off:recamara")

    assert ("hide", "recamara") not in house.log


def test_an_alarm_that_never_turned_the_tv_on_does_not_close_it(house):
    house.hush.hours = QuietHours(time(22, 0), time(7, 30))
    screens = house.build()
    screens.ring(alarm())

    screens.rang(17)

    assert house.timer.armed == {}


def test_a_new_alarm_on_the_same_tv_cancels_the_closing(house):
    screens = house.build()
    screens.ring(alarm())
    screens.rang(17)

    screens.ring(alarm(job_id=18))

    assert "screen-off:recamara" not in house.timer.armed
    assert screens.restore_url("recamara") == alarm_url(18)


def test_the_closing_survives_a_restart(house):
    house.build().ring(alarm(job_id=17, device="recamara"))
    house.build().ring(alarm(job_id=18, device="comedor"))
    first = house.build()
    first.rang(17)
    first.rang(18)
    house.clock.now = NOW + timedelta(minutes=20)
    house.tvs["comedor"].page = alarm_url(18)
    house.timer.armed.clear()

    restarted = house.build()
    restarted.start(house.clock.now, ringing=())

    assert house.log == [("hide", "comedor")]
    assert house.timer.armed == {}


def test_a_pending_closing_is_armed_again_after_a_restart(house):
    screens = house.build()
    screens.ring(alarm())
    screens.rang(17)
    house.timer.armed.clear()

    house.build().start(NOW + timedelta(minutes=5), ringing=())

    when, _ = house.timer.armed["screen-off:recamara"]
    assert when == NOW + OFF_DELAY


def test_an_alarm_that_stopped_while_the_service_was_down_gets_its_closing(house):
    house.build().ring(alarm())

    house.build().start(NOW + timedelta(minutes=40), ringing=())

    when, _ = house.timer.armed["screen-off:recamara"]
    assert when == NOW + timedelta(minutes=40) + OFF_DELAY


def test_an_alarm_still_ringing_after_a_restart_keeps_its_view(house):
    house.build().ring(alarm())

    screens = house.build()
    screens.start(NOW + timedelta(minutes=2), ringing=(17,))

    assert house.timer.armed == {}
    assert screens.restore_url("recamara") == alarm_url()


# --- /pantalla a mano ---


def test_showing_by_hand_puts_the_read_only_kiosk(house):
    screens = house.build()

    assert screens.show("comedor") is True

    assert house.log == [("show", "comedor", KIOSK)]


def test_showing_by_hand_cancels_a_pending_closing(house):
    screens = house.build()
    screens.ring(alarm())
    screens.rang(17)

    screens.show("recamara")

    assert "screen-off:recamara" not in house.timer.armed


def test_showing_by_hand_ignores_the_quiet_hours(house):
    house.hush.hours = QuietHours(time(0, 0), time(23, 59))

    assert house.build().show("comedor") is True


def test_showing_by_hand_respects_the_vacations(house):
    house.hush.start_away(NOW + timedelta(days=3))

    assert house.build().show("comedor") is False

    assert house.log == []


def test_hiding_by_hand_closes_only_our_page_and_cancels_the_closing(house):
    screens = house.build()
    screens.ring(alarm())
    screens.rang(17)
    house.tvs["recamara"].page = KIOSK

    assert screens.hide("recamara") is True
    assert screens.hide("recamara") is False
    assert "screen-off:recamara" not in house.timer.armed


def test_a_tv_is_any_screen_device(house):
    screens = house.build()

    assert screens.is_screen("Recamara")
    assert not screens.is_screen("parlante")


# --- con los recordatorios de verdad ---


class Announcer:
    def __init__(self, registry, log):
        self.registry = registry
        self.log = log

    def __call__(self, job, rings=0, write=True):
        for alias in job.devices:
            self.registry.get(alias).say(job.message)

    def stop(self, devices):
        pass


@pytest.fixture
def wired(house):
    screens = house.build()
    timer = house.timer

    def build():
        return Reminders(
            store=Store(house.path),
            timer=timer,
            announce=Announcer(StubRegistry(**house.tvs), house.log),
            clock=house.clock,
            ringing=RingingStore(house.path),
            quiet=house.hush,
            screen=screens,
        )

    return build


def test_a_firing_alarm_speaks_and_then_shows_its_view(house, wired):
    reminders = wired()
    job = reminders.add(OWNER, NOW, "arriba", device="recamara")

    timer_key = str(job.id)
    house.timer.fire(timer_key)

    assert house.log == [
        ("say", "recamara", "arriba"),
        ("show", "recamara", alarm_url(job.id)),
    ]


def test_turning_the_alarm_off_arms_the_closing(house, wired):
    reminders = wired()
    job = reminders.add(OWNER, NOW, "arriba", device="recamara")
    house.timer.fire(str(job.id))

    reminders.silence(OWNER, job.id, "Eze")

    assert house.timer.armed["screen-off:recamara"][0] == NOW + OFF_DELAY


def test_on_vacation_a_firing_alarm_does_not_turn_the_tv_on(house, wired):
    house.hush.start_away(NOW + timedelta(days=3))
    reminders = wired()
    job = reminders.add(OWNER, NOW, "arriba", device="recamara")

    house.timer.fire(str(job.id))

    assert not [entry for entry in house.log if entry[0] == "show"]


def test_in_the_quiet_hours_a_firing_alarm_does_not_turn_the_tv_on(house, wired):
    house.hush.hours = QuietHours(time(22, 0), time(7, 30))
    reminders = wired()
    job = reminders.add(OWNER, NOW, "arriba", device="recamara")

    house.timer.fire(str(job.id))

    assert not [entry for entry in house.log if entry[0] == "show"]


def test_the_restart_of_the_reminders_arms_the_closing_again(house, wired):
    house.build().ring(alarm(job_id=99))
    house.build().rang(99)
    house.timer.armed.clear()

    wired().start(NOW)

    assert "screen-off:recamara" in house.timer.armed

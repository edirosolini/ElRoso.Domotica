"""«🔕 Apagar» corta una alarma que sigue sonando, desde cualquier chat."""

from datetime import datetime, timedelta

import pytest

from homeauto import main
from homeauto.bot.commands import Commands
from homeauto.schedule.announcer import Announcer
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.history import OFF, HistoryStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.ringing import RingingStore
from homeauto.schedule.store import Store

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
OTHER = 99
NOW = datetime(2026, 10, 15, 7, 0)


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def fire(self, key):
        self.armed[key][1]()


@pytest.fixture
def cmd(tmp_path):
    path = tmp_path / "jobs.db"
    told = []
    speaker = FakeSpeaker()

    def notify(chat_id, text, actions=()):
        told.append((chat_id, text))

    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=notify,
        fallback="parlante",
        actions=main.ALARM_ACTIONS,
        ring_actions=main.OFF_ACTIONS,
        chat_ids=[OWNER, OTHER],
    )
    timer = FakeTimer()
    reminders = Reminders(
        store=Store(path),
        timer=timer,
        announce=announcer,
        fired=FiredStore(path),
        history=HistoryStore(path),
        ringing=RingingStore(path),
        stop_audio=announcer.stop,
        notify=notify,
        clock=lambda: NOW,
        chat_ids=[OWNER, OTHER],
    )
    commands = Commands(
        config=make_config(allowed={OWNER, OTHER}),
        speakers=StubRegistry(parlante=speaker),
        reminders=reminders,
        clock=lambda: NOW,
    )
    commands.told = told
    commands.speaker = speaker
    commands.timer = timer
    return commands


def ring(cmd):
    job = cmd.reminders.add(OWNER, NOW, "arriba")
    cmd.timer.fire(str(job.id))
    cmd.told.clear()
    return job


def test_off_works_from_any_chat_and_tells_the_rest(cmd):
    job = ring(cmd)

    reply = cmd.press(OTHER, f"callar {job.id}", who="Ana")

    assert reply == "🔕 Apagada: «arriba»"
    assert cmd.told == [(OWNER, "🔕 Ana apagó la alarma: «arriba»")]
    assert cmd.speaker.stopped == 1
    assert f"ring:{job.id}" not in cmd.timer.armed
    [entry] = cmd.reminders.history.between(NOW, NOW + timedelta(minutes=1))
    assert (entry.closed, entry.done_by) == (OFF, "Ana")


def test_off_twice_says_it_already_was(cmd):
    job = ring(cmd)
    cmd.press(OWNER, f"callar {job.id}", who="Eze")

    reply = cmd.press(OTHER, f"callar {job.id}", who="Ana")

    assert reply == "Esa alarma ya estaba apagada."
    assert len(cmd.told) == 1


def test_off_without_a_name_still_works(cmd):
    job = ring(cmd)

    cmd.press(OWNER, f"callar {job.id}")

    assert cmd.told == [(OTHER, "🔕 Alguien apagó la alarma: «arriba»")]


def test_off_with_a_bad_number_asks_which(cmd):
    assert cmd.press(OWNER, "callar arriba", who="Eze") == "No sé cuál apagar."


def test_off_is_a_button_and_not_something_to_route_or_type(cmd):
    assert "callar" not in cmd._dispatch()
    assert "callar" not in main.ALL_COMMANDS


def test_a_stranger_cannot_turn_it_off(cmd):
    job = ring(cmd)

    reply = cmd.press(7, f"callar {job.id}", who="Nadie")

    assert "No estás en la lista" in reply
    assert f"ring:{job.id}" in cmd.timer.armed


def test_the_alarm_comes_with_off_and_snooze():
    assert main.ALARM_ACTIONS[0] == ("🔕 Apagar", "callar {job}")
    assert main.ALARM_ACTIONS[1:] == main.SNOOZE_ACTIONS


def test_the_off_button_fits_in_telegram():
    """Telegram rechaza un callback_data de más de 64 bytes."""
    for _label, data in main.ALARM_ACTIONS + main.OFF_ACTIONS:
        assert len(data.format(job=2**63 - 1).encode()) <= 64

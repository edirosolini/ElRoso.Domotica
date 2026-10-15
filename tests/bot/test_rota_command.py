"""`/turnos`: atar una rotación semanal a algo que repite, quitarla y listarlas."""

from datetime import date, datetime, timedelta

import pytest

from homeauto.bot.commands import HELP, Commands, with_actions
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import ALARM, ONCE, REMINDER, WEEKLY, Store

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
OTHER = 99
STRANGER = 7
# Jueves 15 de octubre de 2026: la semana arrancó el lunes 12.
NOW = datetime(2026, 10, 15, 9, 0)
MONDAY = date(2026, 10, 12)


class FakeTimer:
    def schedule(self, key, when, action):
        pass

    def unschedule(self, key):
        pass


@pytest.fixture
def cmd(tmp_path):
    reminders = Reminders(
        store=Store(tmp_path / "jobs.db"),
        timer=FakeTimer(),
        announce=lambda job: None,
        clock=lambda: NOW,
    )
    return Commands(
        config=make_config(allowed={OWNER, OTHER}),
        speakers=StubRegistry(parlante=FakeSpeaker()),
        reminders=reminders,
        clock=lambda: NOW,
    )


def trash(cmd, chat=OWNER, repeat=WEEKLY, kind=REMINDER):
    """Los lunes a las ocho de la noche, sacar la basura."""
    days = [1] if repeat == WEEKLY else None
    return cmd.reminders.add(chat, datetime(2026, 10, 19, 20, 0), "sacar la basura",
                             repeat=repeat, days=days, kind=kind)


def test_binding_a_rota_saves_the_names_and_the_monday_of_this_week(cmd):
    job = trash(cmd)

    reply = cmd.turns(OWNER, f"{job.id} Cin, Die")

    stored = cmd.reminders.get(job.id)
    assert stored.turns == ["Cin", "Die"]
    assert stored.rota_from == MONDAY
    assert f"#{job.id}" in reply and "Cin" in reply and "Die" in reply


def test_the_reply_says_who_goes_next(cmd):
    job = trash(cmd)

    reply = cmd.turns(OWNER, f"{job.id} Cin, Die")

    # El lunes 19 ya es la semana siguiente.
    assert "Le toca a Die" in reply


def test_the_names_can_be_joined_with_y(cmd):
    job = trash(cmd)

    cmd.turns(OWNER, f"#{job.id} Cin y Die")

    assert cmd.reminders.get(job.id).turns == ["Cin", "Die"]


def test_any_chat_can_bind_a_rota_to_any_job(cmd):
    job = trash(cmd, chat=OWNER)

    cmd.turns(OTHER, f"{job.id} Cin, Die")

    assert cmd.reminders.get(job.id).turns == ["Cin", "Die"]


def test_an_alarm_that_repeats_can_rotate(cmd):
    job = trash(cmd, kind=ALARM)

    cmd.turns(OWNER, f"{job.id} Cin, Die")

    assert cmd.reminders.get(job.id).turns == ["Cin", "Die"]


def test_a_timer_cannot_rotate(cmd):
    job = trash(cmd, repeat=ONCE)

    reply = cmd.turns(OWNER, f"{job.id} Cin, Die")

    assert cmd.reminders.get(job.id).rota is None
    assert "una sola vez" in reply


@pytest.mark.parametrize("name", ["Cin2", "Die-go", "Ana_1"])
def test_a_name_that_cannot_be_said_is_rejected(cmd, name):
    job = trash(cmd)

    reply = cmd.turns(OWNER, f"{job.id} Cin, {name}")

    assert cmd.reminders.get(job.id).rota is None
    assert name in reply


def test_a_missing_job_says_so(cmd):
    assert "#99" in cmd.turns(OWNER, "99 Cin, Die")


def test_off_removes_the_rota(cmd):
    job = trash(cmd)
    cmd.turns(OWNER, f"{job.id} Cin, Die")

    reply = cmd.turns(OWNER, f"{job.id} off")

    stored = cmd.reminders.get(job.id)
    assert stored.rota is None and stored.rota_from is None
    assert f"#{job.id}" in reply


def test_without_argument_it_lists_the_rotas(cmd):
    job = trash(cmd)
    trash(cmd, chat=OTHER)
    cmd.turns(OWNER, f"{job.id} Cin, Die")

    reply = cmd.turns(OTHER, "")

    assert f"#{job.id}" in reply and "Cin, Die" in reply and "Le toca a Die" in reply
    assert reply.count("#") == 1


def test_without_rotas_the_list_says_how_to_start(cmd):
    assert "/turnos 7 Cin, Die" in cmd.turns(OWNER, "")


def test_a_malformed_argument_shows_how(cmd):
    assert "/turnos 7 Cin, Die" in cmd.turns(OWNER, "Cin, Die")


def test_a_stranger_cannot_touch_the_rotas(cmd):
    job = trash(cmd)

    cmd.turns(STRANGER, f"{job.id} Cin, Die")

    assert cmd.reminders.get(job.id).rota is None


def test_the_list_shows_the_rota(cmd):
    job = trash(cmd)
    cmd.turns(OWNER, f"{job.id} Cin, Die")

    reply = with_actions(cmd.list, OWNER).text

    line = next(line for line in reply.splitlines() if f"#{job.id}" in line)
    assert "Cin, Die" in line


def test_the_router_can_reach_it(cmd):
    job = trash(cmd)

    cmd._dispatch()["turnos"](OWNER, f"{job.id} Cin, Die")

    assert cmd.reminders.get(job.id).turns == ["Cin", "Die"]


def test_help_explains_the_turns():
    assert "/turnos 7 Cin, Die" in HELP
    assert "/turnos 7 off" in HELP

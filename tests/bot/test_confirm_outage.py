"""«✅ Confirmar» corta los re-avisos de una caída, solo desde un chat de alertas."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from homeauto import main
from homeauto.bot.commands import Commands
from homeauto.watch.checks import Check, CheckResult
from homeauto.watch.monitor import Monitor
from homeauto.watch.status import StatusStore

from tests.conftest import StubRegistry, make_config

OWNER = 42
PARTNER = 43
OTHER = 77
NOW = datetime(2026, 10, 15, 3, 0)


@pytest.fixture
def cmd(tmp_path):
    clock = {"now": NOW}
    up = {"vps": False}
    told = []
    reminded = []
    monitor = Monitor(
        checks=[Check(name="vps", host="10.0.0.1", port=443)],
        store=StatusStore(tmp_path / "jobs.db"),
        announce=lambda text, urgent, detail="", check="": None,
        remind=lambda text, name, detail="": reminded.append(name),
        tell_others=lambda chat_id, text: main._tell_alert_chats(
            lambda chat, message: told.append((chat, message)), {OWNER, PARTNER}, chat_id, text
        ),
        run=lambda check, http, tcp: CheckResult(check.name, up[check.name], "timeout"),
        clock=lambda: clock["now"],
    )
    config = replace(
        make_config(allowed={OWNER, PARTNER, OTHER}), alert_chat_ids=frozenset({OWNER, PARTNER})
    )
    commands = Commands(config=config, speakers=StubRegistry(), monitor=monitor)
    commands.told = told
    commands.reminded = reminded
    commands.up = up

    def tick(minutes=1):
        for _ in range(minutes):
            clock["now"] += timedelta(minutes=1)
            monitor.run_once()

    commands.tick = tick
    return commands


def declare(cmd):
    cmd.monitor.run_once()
    cmd.tick()


def test_an_alert_chat_confirms_and_the_other_alert_chats_hear_it(cmd):
    declare(cmd)

    reply = cmd.press(OWNER, "confirmar vps", who="Eze")

    assert reply.startswith("✅ Confirmado: vps")
    assert cmd.told == [(PARTNER, "✅ Eze confirmó: vps no responde")]


def test_a_confirmed_outage_stops_reminding(cmd):
    declare(cmd)
    cmd.press(OWNER, "confirmar vps", who="Eze")

    cmd.tick(60)

    assert cmd.reminded == []


def test_a_chat_outside_the_alert_chats_cannot_confirm(cmd):
    declare(cmd)

    reply = cmd.press(OTHER, "confirmar vps", who="Ana")

    assert "alertas" in reply
    assert cmd.told == []
    cmd.tick(5)
    assert cmd.reminded == ["vps"], "rechazado no confirma"


def test_a_stranger_cannot_confirm(cmd):
    declare(cmd)

    reply = cmd.press(7, "confirmar vps", who="Nadie")

    assert "No estás en la lista" in reply


def test_confirming_twice_says_it_already_was(cmd):
    declare(cmd)
    cmd.press(OWNER, "confirmar vps", who="Eze")

    reply = cmd.press(PARTNER, "confirmar vps", who="Ana")

    assert "ya estaba confirmada" in reply
    assert len(cmd.told) == 1


def test_confirming_a_service_that_came_back_says_so(cmd):
    declare(cmd)
    cmd.up["vps"] = True
    cmd.tick()

    assert cmd.press(OWNER, "confirmar vps", who="Eze") == "vps ya volvió a responder."


def test_confirming_without_a_name_asks_which(cmd):
    assert cmd.press(OWNER, "confirmar", who="Eze") == "No sé cuál confirmar."


def test_without_a_monitor_there_is_nothing_to_confirm():
    commands = Commands(config=make_config(allowed={OWNER}), speakers=StubRegistry())

    assert "No vigilo" in commands.press(OWNER, "confirmar vps", who="Eze")


def test_confirm_is_a_button_and_not_something_to_route_or_type(cmd):
    assert "confirmar" not in cmd._dispatch()
    assert "confirmar" not in main.ALL_COMMANDS

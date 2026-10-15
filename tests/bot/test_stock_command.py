"""`/pastillas`: listar, atar un recordatorio a un remedio, reponer y cambiar el aviso."""

from datetime import datetime, timedelta

import pytest

from homeauto.bot.commands import HELP, Commands
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.stock import STOCK_ALERT, StockStore
from homeauto.schedule.store import ALARM, DAILY, ONCE, REMINDER, Store

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
STRANGER = 7
NOW = datetime(2026, 10, 15, 7, 0)


class FakeTimer:
    def schedule(self, key, when, action):
        pass

    def unschedule(self, key):
        pass


@pytest.fixture
def cmd(tmp_path):
    path = tmp_path / "jobs.db"
    reminders = Reminders(
        store=Store(path),
        timer=FakeTimer(),
        announce=lambda job: None,
        awaiting=AwaitingStore(path),
        clock=lambda: NOW,
    )
    return Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker()),
        reminders=reminders,
        stock=StockStore(path),
        clock=lambda: NOW,
    )


def reminder(cmd, repeat=DAILY, kind=REMINDER):
    return cmd.reminders.add(OWNER, NOW + timedelta(hours=1), "tomar enalapril",
                             repeat=repeat, kind=kind)


def test_without_stocks_it_says_so(cmd):
    assert "No estoy contando" in cmd.pills(OWNER, "")


def test_binding_a_reminder_creates_the_stock(cmd):
    job = reminder(cmd)

    reply = cmd.pills(OWNER, f"{job.id} enalapril 30")

    supply = cmd.stock.find("enalapril")
    assert supply.count == 30
    assert cmd.reminders.get(job.id).stock_id == supply.id
    assert f"#{job.id}" in reply and "enalapril" in reply and "30" in reply


def test_binding_to_an_existing_stock_sets_the_count(cmd):
    first, second = reminder(cmd), reminder(cmd)
    cmd.pills(OWNER, f"{first.id} enalapril 30")

    reply = cmd.pills(OWNER, f"{second.id} Enalapril 99")

    supply = cmd.stock.find("enalapril")
    assert supply.count == 99
    assert cmd.reminders.get(second.id).stock_id == supply.id
    assert "fijé" in reply.lower() and "99" in reply


def test_setting_the_count_above_the_threshold_rearms_the_warning(cmd):
    first, second = reminder(cmd), reminder(cmd)
    cmd.pills(OWNER, f"{first.id} enalapril {STOCK_ALERT + 1}")
    cmd.stock.take_dose(cmd.stock.find("enalapril").id)

    cmd.pills(OWNER, f"{second.id} enalapril 30")

    assert not cmd.stock.find("enalapril").alerted


def test_raising_the_threshold_over_what_is_left_warns_in_the_reply(cmd):
    job = reminder(cmd)
    cmd.pills(OWNER, f"{job.id} enalapril 5")

    reply = cmd.pills(OWNER, "enalapril aviso 5")

    assert "Ojo: ya quedan 5, por debajo del aviso." in reply


def test_a_threshold_under_what_is_left_says_nothing_more(cmd):
    job = reminder(cmd)
    cmd.pills(OWNER, f"{job.id} enalapril 30")

    assert "Ojo" not in cmd.pills(OWNER, "enalapril aviso 5")


def test_an_already_warned_stock_is_not_warned_again_in_the_reply(cmd):
    job = reminder(cmd)
    cmd.pills(OWNER, f"{job.id} enalapril {STOCK_ALERT}")
    cmd.stock.take_dose(cmd.stock.find("enalapril").id)

    assert "Ojo" not in cmd.pills(OWNER, f"enalapril aviso {STOCK_ALERT + 5}")


def test_a_new_stock_needs_a_count(cmd):
    job = reminder(cmd)

    reply = cmd.pills(OWNER, f"{job.id} enalapril")

    assert cmd.stock.find("enalapril") is None
    assert "cuántas" in reply.lower()


def test_an_existing_stock_binds_without_a_count(cmd):
    first, second = reminder(cmd), reminder(cmd)
    cmd.pills(OWNER, f"{first.id} enalapril 30")

    cmd.pills(OWNER, f"{second.id} enalapril")

    assert cmd.reminders.get(second.id).stock_id == cmd.stock.find("enalapril").id


def test_an_unknown_job_is_an_error(cmd):
    reply = cmd.pills(OWNER, "999 enalapril 30")

    assert "#999" in reply
    assert cmd.stock.find("enalapril") is None


def test_only_a_reminder_can_be_bound(cmd):
    job = reminder(cmd, kind=ALARM)

    reply = cmd.pills(OWNER, f"{job.id} enalapril 30")

    assert "recordatorio" in reply
    assert cmd.stock.find("enalapril") is None


def test_only_a_reminder_that_repeats_can_be_bound(cmd):
    job = reminder(cmd, repeat=ONCE)

    reply = cmd.pills(OWNER, f"{job.id} enalapril 30")

    assert "repite" in reply
    assert cmd.stock.find("enalapril") is None


def test_restocking(cmd):
    job = reminder(cmd)
    cmd.pills(OWNER, f"{job.id} enalapril 3")

    reply = cmd.pills(OWNER, "enalapril +30")

    assert cmd.stock.find("enalapril").count == 33
    assert "33" in reply


def test_restocking_an_unknown_pill_is_an_error(cmd):
    reply = cmd.pills(OWNER, "ibuprofeno +30")

    assert "ibuprofeno" in reply
    assert cmd.stock.find("ibuprofeno") is None


def test_changing_the_threshold(cmd):
    job = reminder(cmd)
    cmd.pills(OWNER, f"{job.id} enalapril 30")

    reply = cmd.pills(OWNER, "enalapril aviso 5")

    assert cmd.stock.find("enalapril").threshold == 5
    assert "5" in reply


def test_changing_the_threshold_of_an_unknown_pill_is_an_error(cmd):
    assert "ibuprofeno" in cmd.pills(OWNER, "ibuprofeno aviso 5")


def test_the_list_shows_what_is_left_and_when_it_warns(cmd):
    job = reminder(cmd)
    cmd.pills(OWNER, f"{job.id} enalapril 30")

    reply = cmd.pills(OWNER, "")

    assert "enalapril" in reply
    assert "30" in reply
    assert str(STOCK_ALERT) in reply


def test_something_unreadable_explains_the_forms(cmd):
    reply = cmd.pills(OWNER, "cualquier cosa")

    assert "/pastillas 7 enalapril 30" in reply


def test_a_stranger_is_turned_away(cmd):
    assert "No estás en la lista" in cmd.pills(STRANGER, "")


def test_without_a_stock_store_it_says_so(tmp_path):
    commands = Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker()),
    )

    assert "No tengo" in commands.pills(OWNER, "")


def test_it_is_dispatched_by_name(cmd):
    assert cmd._dispatch()["pastillas"] == cmd.pills


def test_the_help_explains_it():
    assert "/pastillas 7 enalapril 30" in HELP
    assert "/pastillas enalapril +30" in HELP
    assert "/pastillas enalapril aviso 5" in HELP

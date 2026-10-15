"""`StockStore`: cuántas dosis quedan de cada remedio, y la columna que ata un job a su stock."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.stock import STOCK_ALERT, StockStore
from homeauto.schedule.store import DAILY, REMINDER, Store

NOW = datetime(2026, 10, 15, 8, 0)


@pytest.fixture
def stock(tmp_path):
    return StockStore(tmp_path / "jobs.db")


def test_a_new_stock_starts_with_the_default_threshold(stock):
    created, is_new = stock.ensure("Enalapril", 30)

    assert is_new
    assert (created.name, created.count, created.threshold, created.alerted) == (
        "enalapril", 30, STOCK_ALERT, False
    )


def test_the_name_is_unique_regardless_of_case(stock):
    first, _ = stock.ensure("enalapril", 30)

    again, is_new = stock.ensure("ENALAPRIL", 99)

    assert not is_new
    assert again.id == first.id
    assert again.count == 30, "si ya existe no se pisa lo que queda"
    assert stock.find("EnAlApRiL").id == first.id
    assert len(stock.all()) == 1


def test_the_table_has_the_agreed_columns(tmp_path):
    StockStore(tmp_path / "jobs.db")

    with sqlite3.connect(tmp_path / "jobs.db") as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(pill_stock)")]

    assert columns == ["id", "name", "count", "threshold", "alerted"]


def test_a_dose_is_taken_one_at_a_time(stock):
    created, _ = stock.ensure("enalapril", 30)

    taken, alert = stock.take_dose(created.id)

    assert taken.count == 29
    assert not alert


def test_crossing_the_threshold_alerts_once(stock):
    created, _ = stock.ensure("enalapril", STOCK_ALERT + 1)

    first, alert = stock.take_dose(created.id)
    second, again = stock.take_dose(created.id)

    assert (first.count, alert) == (STOCK_ALERT, True)
    assert first.alerted
    assert (second.count, again) == (STOCK_ALERT - 1, False)


def test_the_stock_never_goes_below_zero(stock):
    created, _ = stock.ensure("enalapril", 0)

    taken, _ = stock.take_dose(created.id)

    assert taken.count == 0


def test_an_unknown_stock_takes_nothing(stock):
    assert stock.take_dose(999) is None


def test_restocking_above_the_threshold_rearms_the_alert(stock):
    created, _ = stock.ensure("enalapril", STOCK_ALERT + 1)
    stock.take_dose(created.id)

    restocked = stock.restock("enalapril", 30)

    assert restocked.count == STOCK_ALERT + 30
    assert not restocked.alerted
    for _ in range(30):
        taken, alert = stock.take_dose(created.id)
    assert (taken.count, alert) == (STOCK_ALERT, True)


def test_restocking_below_the_threshold_keeps_it_alerted(stock):
    created, _ = stock.ensure("enalapril", 1)
    stock.take_dose(created.id)

    restocked = stock.restock("enalapril", 2)

    assert restocked.count == 2
    assert restocked.alerted


def test_restocking_an_unknown_stock_is_none(stock):
    assert stock.restock("ibuprofeno", 10) is None


def test_the_threshold_can_be_changed(stock):
    stock.ensure("enalapril", 30)

    changed = stock.set_threshold("Enalapril", 5)

    assert changed.threshold == 5
    assert stock.set_threshold("ibuprofeno", 5) is None


def test_lowering_the_threshold_under_the_count_rearms_the_alert(stock):
    created, _ = stock.ensure("enalapril", 8)
    stock.take_dose(created.id)

    changed = stock.set_threshold("enalapril", 3)

    assert not changed.alerted


def test_a_job_carries_its_stock(tmp_path):
    store = Store(tmp_path / "jobs.db")
    job = store.add(42, NOW, "la pastilla", repeat=DAILY, kind=REMINDER)

    assert job.stock_id is None
    assert store.attach_stock(job.id, 3)
    assert store.get(job.id).stock_id == 3
    assert not store.attach_stock(999, 3)


def test_a_job_can_be_born_with_its_stock(tmp_path):
    store = Store(tmp_path / "jobs.db")

    job = store.add(42, NOW, "la pastilla", kind=REMINDER, stock_id=3)

    assert job.stock_id == 3
    assert store.get(job.id).stock_id == 3


def test_editing_from_the_screen_keeps_the_stock(tmp_path):
    store = Store(tmp_path / "jobs.db")
    job = store.add(42, NOW, "la pastilla", repeat=DAILY, kind=REMINDER)
    store.attach_stock(job.id, 3)

    store.update(job.id, NOW + timedelta(hours=1), "la pastilla roja", repeat=DAILY, kind=REMINDER)

    assert store.get(job.id).stock_id == 3


def test_an_old_jobs_table_gets_the_column(tmp_path):
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,"
            " fires_at TEXT NOT NULL, message TEXT NOT NULL, repeat TEXT NOT NULL DEFAULT 'once')"
        )
        conn.execute("INSERT INTO jobs (chat_id, fires_at, message) VALUES (42, ?, 'x')", (NOW.isoformat(),))

    [job] = Store(path).pending()

    assert job.stock_id is None


def test_what_fired_remembers_its_stock(tmp_path):
    fired = FiredStore(tmp_path / "jobs.db")

    fired.remember(42, "la pastilla", None, NOW, REMINDER, 7, stock_id=3)

    assert fired.last(42).stock_id == 3


def test_an_old_last_fired_table_gets_the_column(tmp_path):
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE last_fired (chat_id INTEGER PRIMARY KEY, message TEXT NOT NULL,"
            " device TEXT, fired_at TEXT NOT NULL)"
        )

    fired = FiredStore(path)
    fired.remember(42, "x", None, NOW)

    assert fired.last(42).stock_id is None


def test_what_awaits_its_done_remembers_its_stock(tmp_path):
    awaiting = AwaitingStore(tmp_path / "jobs.db")

    awaiting.remember(7, "la pastilla", NOW, stock_id=3)

    assert awaiting.get(7).stock_id == 3


def test_an_old_awaiting_table_gets_the_column(tmp_path):
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE awaiting_done (job_id INTEGER PRIMARY KEY, message TEXT NOT NULL,"
            " fired_at TEXT NOT NULL)"
        )

    awaiting = AwaitingStore(path)
    awaiting.remember(7, "x", NOW)

    assert awaiting.get(7).stock_id is None


def test_the_count_can_be_set(stock):
    stock.ensure("enalapril", 30)

    changed = stock.set_count("Enalapril", 12)

    assert changed.count == 12
    assert stock.set_count("ibuprofeno", 5) is None


def test_setting_the_count_above_the_threshold_rearms_the_alert(stock):
    created, _ = stock.ensure("enalapril", STOCK_ALERT)
    stock.take_dose(created.id)

    assert not stock.set_count("enalapril", 30).alerted


def test_setting_the_count_below_the_threshold_keeps_it_alerted(stock):
    created, _ = stock.ensure("enalapril", STOCK_ALERT)
    stock.take_dose(created.id)

    assert stock.set_count("enalapril", 2).alerted


def test_raising_the_threshold_over_the_count_does_not_alert_on_the_spot(stock):
    stock.ensure("enalapril", 5)

    changed = stock.set_threshold("enalapril", 10)

    assert not changed.alerted

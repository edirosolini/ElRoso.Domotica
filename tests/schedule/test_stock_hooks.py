"""Lo que `Reminders` hace con el stock al sonar, posponer y marcar «Hecho»."""

from datetime import datetime, timedelta

import pytest

from homeauto.lists import SHOPPING, ListStore
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.stock import STOCK_ALERT, StockStore
from homeauto.schedule.store import DAILY, REMINDER, Store

OWNER = 42
OTHER = 99
NOW = datetime(2026, 10, 15, 8, 0)
SOON = NOW + timedelta(minutes=5)


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def fire(self, key):
        self.armed[key][1]()


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class BrokenStock:
    def take_dose(self, stock_id):
        raise RuntimeError("disco lleno")


@pytest.fixture
def house(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    clock = Clock(NOW)
    stock = StockStore(path)
    lists = ListStore(path)
    sent = []

    def build(stock=stock):
        return Reminders(
            store=Store(path),
            timer=timer,
            announce=lambda job: None,
            fired=FiredStore(path),
            awaiting=AwaitingStore(path),
            notify=lambda chat, text, *rest: sent.append((chat, text)),
            clock=clock,
            chat_ids=(OWNER, OTHER),
            stock=stock,
            lists=lists,
        )

    return build, timer, clock, stock, lists, sent


def pill(reminders, stock, count, at=SOON, name="enalapril"):
    """Un recordatorio diario atado a un stock con `count` dosis."""
    supply, _ = stock.ensure(name, count)
    job = reminders.add(OWNER, at, f"tomar {name}", repeat=DAILY, kind=REMINDER)
    reminders.store.attach_stock(job.id, supply.id)
    return job, supply


def ring(timer, clock, job, at=SOON):
    clock.now = at
    timer.fire(str(job.id))


def test_done_takes_one_dose(house):
    build, timer, clock, stock, _, _ = house
    reminders = build()
    job, supply = pill(reminders, stock, 30)
    ring(timer, clock, job)

    reminders.done(OWNER, job.id, "Eze")

    assert stock.get(supply.id).count == 29


def test_a_second_tap_does_not_take_a_second_dose(house):
    build, timer, clock, stock, _, _ = house
    reminders = build()
    job, supply = pill(reminders, stock, 30)
    ring(timer, clock, job)

    reminders.done(OWNER, job.id, "Eze")
    reminders.done(OTHER, job.id, "Ana")

    assert stock.get(supply.id).count == 29


def test_a_reminder_without_stock_takes_nothing(house):
    build, timer, clock, stock, _, _ = house
    reminders = build()
    supply, _ = stock.ensure("enalapril", 30)
    job = reminders.add(OWNER, SOON, "regar", repeat=DAILY, kind=REMINDER)
    ring(timer, clock, job)

    assert reminders.done(OWNER, job.id, "Eze") == "regar"
    assert stock.get(supply.id).count == 30


def test_crossing_the_threshold_tells_everyone_and_adds_it_to_the_shopping_list(house):
    build, timer, clock, stock, lists, sent = house
    reminders = build()
    job, _ = pill(reminders, stock, STOCK_ALERT + 1)
    ring(timer, clock, job)

    reminders.done(OWNER, job.id, "Eze")

    warning = f"💊 Quedan {STOCK_ALERT} de enalapril, comprar."
    assert (OWNER, warning) in sent
    assert (OTHER, warning) in sent
    assert lists.items(SHOPPING) == ["enalapril"]


def test_the_warning_goes_out_once(house):
    build, timer, clock, stock, lists, sent = house
    reminders = build()
    job, _ = pill(reminders, stock, STOCK_ALERT + 1)
    ring(timer, clock, job)
    reminders.done(OWNER, job.id, "Eze")
    sent.clear()

    tomorrow = SOON + timedelta(days=1)
    ring(timer, clock, job, tomorrow)
    reminders.done(OWNER, job.id, "Eze")

    assert not [text for _, text in sent if text.startswith("💊")]
    assert lists.items(SHOPPING) == ["enalapril"]


def test_with_nothing_left_it_says_none_are_left(house):
    build, timer, clock, stock, _, sent = house
    reminders = build()
    job, supply = pill(reminders, stock, 1)
    stock.set_threshold("enalapril", 0)
    ring(timer, clock, job)

    reminders.done(OWNER, job.id, "Eze")

    assert stock.get(supply.id).count == 0
    assert (OWNER, "💊 No quedan de enalapril, comprar.") in sent


def test_an_item_already_on_the_shopping_list_is_not_repeated(house):
    build, timer, clock, stock, lists, _ = house
    lists.add(SHOPPING, ["Enalapril"])
    reminders = build()
    job, _ = pill(reminders, stock, STOCK_ALERT + 1)
    ring(timer, clock, job)

    reminders.done(OWNER, job.id, "Eze")

    assert lists.items(SHOPPING) == ["Enalapril"]


def test_two_reminders_share_one_stock(house):
    build, timer, clock, stock, _, _ = house
    reminders = build()
    morning, supply = pill(reminders, stock, 30)
    evening = reminders.add(OWNER, SOON + timedelta(hours=12), "tomar enalapril", repeat=DAILY,
                            kind=REMINDER)
    reminders.store.attach_stock(evening.id, supply.id)

    ring(timer, clock, morning)
    reminders.done(OWNER, morning.id, "Eze")
    ring(timer, clock, evening, SOON + timedelta(hours=12))
    reminders.done(OWNER, evening.id, "Eze")

    assert stock.get(supply.id).count == 28


def test_a_postponed_reminder_takes_from_the_same_stock(house):
    build, timer, clock, stock, _, _ = house
    reminders = build()
    supply, _ = stock.ensure("enalapril", 30)
    job = reminders.add(OWNER, SOON, "tomar enalapril", kind=REMINDER, stock_id=supply.id)
    ring(timer, clock, job)

    snoozed = reminders.snooze(OWNER, timedelta(minutes=10))
    assert reminders.store.get(job.id) is None, "el original de una sola vez ya no está"
    assert snoozed.stock_id == supply.id
    ring(timer, clock, snoozed, SOON + timedelta(minutes=10))
    reminders.done(OWNER, snoozed.id, "Eze")

    assert stock.get(supply.id).count == 29


def test_a_broken_stock_does_not_cost_the_done(house):
    build, timer, clock, stock, _, sent = house
    reminders = build(stock=BrokenStock())
    job, _ = pill(reminders, stock, 30)
    ring(timer, clock, job)

    assert reminders.done(OWNER, job.id, "Eze") == "tomar enalapril"
    assert (OTHER, "✅ Eze marcó hecho: «tomar enalapril»") in sent


def test_without_a_stock_store_done_still_works(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    clock = Clock(NOW)
    reminders = Reminders(
        store=Store(path), timer=timer, announce=lambda job: None,
        awaiting=AwaitingStore(path), clock=clock,
    )
    job = reminders.add(OWNER, SOON, "tomar", repeat=DAILY, kind=REMINDER, stock_id=3)
    ring(timer, clock, job)

    assert reminders.done(OWNER, job.id, "Eze") == "tomar"

"""Lo que saltea feriados se decide al sonar: no anuncia, deja rastro y se reagenda."""

from datetime import date, datetime, timedelta

import pytest

from homeauto.holidays import BRIDGE, FIXED, MOVABLE, Holiday
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.history import HOLIDAY, HistoryStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.ringing import RingingStore
from homeauto.schedule.store import ALARM, REMINDER, WEEKLY, Store

OWNER = 42
OTHER = 99
WORKDAYS = (1, 2, 3, 4, 5)
# Lunes 12 de octubre de 2026, feriado trasladable.
COLUMBUS = datetime(2026, 10, 12, 7, 0)
TUESDAY = COLUMBUS + timedelta(days=1)
DAY = (COLUMBUS - timedelta(days=1), COLUMBUS + timedelta(days=2))
NAME = "Día del Respeto a la Diversidad Cultural"


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def fire(self, key):
        self.armed[key][1]()


class Calendar:
    """La caché local de feriados: un dict por día que anota qué se le preguntó."""

    def __init__(self, *holidays, broken=False):
        self.by_day = {holiday.day: holiday for holiday in holidays}
        self.asked = []
        self.broken = broken

    def __call__(self, day):
        self.asked.append(day)
        if self.broken:
            raise RuntimeError("la base no contesta")
        return self.by_day.get(day)


COLUMBUS_DAY = Holiday(COLUMBUS.date(), MOVABLE, NAME)


@pytest.fixture
def parts(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    said = []
    told = []

    def build(holidays=Calendar(COLUMBUS_DAY)):
        return Reminders(
            store=Store(path),
            timer=timer,
            announce=lambda job, **kwargs: said.append(job.message),
            fired=FiredStore(path),
            awaiting=AwaitingStore(path),
            history=HistoryStore(path),
            ringing=RingingStore(path),
            notify=lambda chat, text, *actions: told.append((chat, text)),
            clock=lambda: COLUMBUS,
            chat_ids=(OWNER, OTHER),
            holidays=holidays,
        )

    return {
        "build": build, "timer": timer, "said": said, "told": told, "path": path,
    }


def ring_on(reminders, timer, when=COLUMBUS, kind=REMINDER, skip=True, message="el colegio"):
    job = reminders.store.add(
        OWNER, when, message, repeat=WEEKLY, days=WORKDAYS, kind=kind, skip_holidays=skip
    )
    reminders._arm(job)
    timer.fire(str(job.id))
    return job


def test_on_a_holiday_it_does_not_announce(parts):
    reminders = parts["build"]()

    ring_on(reminders, parts["timer"])

    assert parts["said"] == []


def test_on_a_holiday_nothing_waits_for_a_button(parts):
    reminders = parts["build"]()

    job = ring_on(reminders, parts["timer"], kind=ALARM)

    assert FiredStore(parts["path"]).last(OWNER) is None
    assert AwaitingStore(parts["path"]).get(job.id) is None
    assert RingingStore(parts["path"]).get(job.id) is None
    assert f"nag:{job.id}" not in parts["timer"].armed
    assert f"ring:{job.id}" not in parts["timer"].armed


def test_a_reminder_on_a_holiday_does_not_wait_for_done(parts):
    reminders = parts["build"]()

    job = ring_on(reminders, parts["timer"], kind=REMINDER)

    assert AwaitingStore(parts["path"]).get(job.id) is None


def test_on_a_holiday_the_history_keeps_it_closed_as_holiday(parts):
    reminders = parts["build"]()

    job = ring_on(reminders, parts["timer"])

    [entry] = HistoryStore(parts["path"]).between(*DAY)
    assert entry.job_id == job.id
    assert entry.closed == HOLIDAY
    assert entry.closed_at == COLUMBUS
    assert entry.announced is False


def test_on_a_holiday_it_moves_on_to_the_next_day(parts):
    reminders = parts["build"]()

    job = ring_on(reminders, parts["timer"])

    assert reminders.store.get(job.id).when == TUESDAY
    assert parts["timer"].armed[str(job.id)][0] == TUESDAY


def test_on_a_holiday_every_chat_is_told_why_it_did_not_ring(parts):
    reminders = parts["build"]()

    ring_on(reminders, parts["timer"])

    expected = f"🏖 Feriado ({NAME}): hoy no suena «el colegio»"
    assert parts["told"] == [(OWNER, expected), (OTHER, expected)]


def test_the_holiday_is_looked_up_for_the_day_it_was_due(parts):
    calendar = Calendar(COLUMBUS_DAY)
    reminders = parts["build"](calendar)

    ring_on(reminders, parts["timer"])

    assert calendar.asked == [date(2026, 10, 12)]


def test_on_a_working_day_it_rings_as_always(parts):
    reminders = parts["build"]()

    ring_on(reminders, parts["timer"], when=TUESDAY)

    assert parts["said"] == ["el colegio"]
    assert parts["told"] == []


def test_without_the_flag_it_rings_on_a_holiday(parts):
    reminders = parts["build"]()

    ring_on(reminders, parts["timer"], skip=False)

    assert parts["said"] == ["el colegio"]


def test_a_bridge_rings(parts):
    reminders = parts["build"](Calendar(Holiday(COLUMBUS.date(), BRIDGE, "Puente")))

    ring_on(reminders, parts["timer"])

    assert parts["said"] == ["el colegio"]


def test_a_fixed_holiday_also_skips(parts):
    reminders = parts["build"](Calendar(Holiday(COLUMBUS.date(), FIXED, "Otro feriado")))

    ring_on(reminders, parts["timer"])

    assert parts["said"] == []


def test_without_holidays_it_rings(parts):
    reminders = parts["build"](None)

    ring_on(reminders, parts["timer"])

    assert parts["said"] == ["el colegio"]


def test_a_broken_holiday_cache_lets_it_ring(parts):
    reminders = parts["build"](Calendar(COLUMBUS_DAY, broken=True))

    ring_on(reminders, parts["timer"])

    assert parts["said"] == ["el colegio"]


def test_a_missed_holiday_after_a_restart_is_skipped_too(parts):
    reminders = parts["build"]()
    reminders.store.add(
        OWNER, COLUMBUS, "el colegio", repeat=WEEKLY, days=WORKDAYS, skip_holidays=True
    )

    reminders.start(now=COLUMBUS + timedelta(hours=1))

    assert parts["said"] == []
    assert len(parts["told"]) == 2


def test_add_and_update_keep_the_flag(parts):
    reminders = parts["build"]()

    job = reminders.add(
        OWNER, TUESDAY, "el colegio", repeat=WEEKLY, days=WORKDAYS, skip_holidays=True
    )
    assert reminders.store.get(job.id).skip_holidays is True

    updated = reminders.update(job.id, TUESDAY, "el colegio", repeat=WEEKLY, days=WORKDAYS)
    assert updated.skip_holidays is False

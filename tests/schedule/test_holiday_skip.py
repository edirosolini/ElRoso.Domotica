"""Lo que saltea feriados se decide al sonar: no anuncia, deja rastro y se reagenda."""

import threading
import time
from datetime import date, datetime, timedelta

import pytest

from homeauto.holidays import BRIDGE, FIXED, MOVABLE, Holiday
from homeauto.people import Household, PersonStore
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.history import HOLIDAY, HistoryStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.ringing import RingingStore
from homeauto.schedule.store import ALARM, EVERYONE, PERSON, REMINDER, WEEKLY, Store
from homeauto.watch.marks import Marks

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
    household = Household(PersonStore(path), (OWNER, OTHER))
    people = {"cin": household.add("Cin", OWNER), "die": household.add("Die")}

    def build(holidays=Calendar(COLUMBUS_DAY), marks=Marks(path)):
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
            resolve=household.get,
            find=household.by_name,
            marks=marks,
        )

    return {
        "build": build, "timer": timer, "said": said, "told": told, "path": path,
        "people": people,
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

    expected = f"🏖 Hoy es feriado ({NAME}), no suena:\n• 07:00 «el colegio»"
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


def plan(reminders, at, message, **kwargs):
    """Agenda un aviso `hábiles` para hoy, sin dispararlo."""
    job = reminders.store.add(
        OWNER, at, message, repeat=WEEKLY, days=WORKDAYS, kind=kwargs.pop("kind", REMINDER),
        skip_holidays=True, **kwargs,
    )
    reminders._arm(job)
    return job


def at(hour, minute=0):
    return COLUMBUS.replace(hour=hour, minute=minute)


def test_two_skipped_today_go_in_one_message_and_the_second_says_nothing(parts):
    reminders = parts["build"]()
    first = plan(reminders, at(7), "el colegio")
    second = plan(reminders, at(9, 30), "la basura")

    parts["timer"].fire(str(first.id))
    parts["timer"].fire(str(second.id))

    expected = (
        f"🏖 Hoy es feriado ({NAME}), no suenan:\n"
        "• 07:00 «el colegio»\n"
        "• 09:30 «la basura»"
    )
    assert parts["told"] == [(OWNER, expected), (OTHER, expected)]


def test_each_chat_only_lists_its_own(parts):
    reminders = parts["build"]()
    cin, die = parts["people"]["cin"], parts["people"]["die"]
    mine = plan(reminders, at(7), "el colegio", assignee=PERSON, assignee_id=cin.id)
    plan(reminders, at(8), "la basura")
    plan(reminders, at(9), "las plantas", assignee=EVERYONE)
    plan(reminders, at(10), "el perro", assignee=PERSON, assignee_id=die.id)

    parts["timer"].fire(str(mine.id))

    assert parts["told"] == [
        (OWNER, f"🏖 Hoy es feriado ({NAME}), no suenan:\n"
                "• 07:00 «el colegio»\n• 08:00 «la basura»\n"
                "• 09:00 «las plantas»\n• 10:00 «el perro»"),
        (OTHER, f"🏖 Hoy es feriado ({NAME}), no suenan:\n"
                "• 08:00 «la basura»\n• 09:00 «las plantas»\n• 10:00 «el perro»"),
    ]


def test_a_chat_without_its_own_gets_nothing(parts):
    reminders = parts["build"]()
    cin = parts["people"]["cin"]
    mine = plan(reminders, at(7), "el colegio", assignee=PERSON, assignee_id=cin.id)

    parts["timer"].fire(str(mine.id))

    assert [chat for chat, _ in parts["told"]] == [OWNER]


def test_the_turn_decides_the_chats_as_when_it_rings(parts):
    reminders = parts["build"]()
    turn = plan(reminders, at(7), "la basura")
    reminders.set_rota(turn.id, ["Cin", "Die"], COLUMBUS.date())

    parts["timer"].fire(str(turn.id))

    assert parts["told"] == [
        (OWNER, f"🏖 Hoy es feriado ({NAME}), no suena:\n• 07:00 «Le toca a Cin: la basura»"),
    ]


def test_one_created_after_the_summary_says_its_own_line(parts):
    reminders = parts["build"]()
    first = plan(reminders, at(7), "el colegio")
    parts["timer"].fire(str(first.id))
    parts["told"].clear()

    late = reminders.add(
        OWNER, at(11), "el remedio", repeat=WEEKLY, days=WORKDAYS, kind=REMINDER,
        skip_holidays=True,
    )
    parts["timer"].fire(str(late.id))

    line = "🏖 Hoy es feriado: tampoco suena «el remedio»"
    assert parts["told"] == [(OWNER, line), (OTHER, line)]


def test_one_edited_after_the_summary_says_its_own_line(parts):
    reminders = parts["build"]()
    first = plan(reminders, at(7), "el colegio")
    second = plan(reminders, at(9), "la basura")
    parts["timer"].fire(str(first.id))
    parts["told"].clear()

    reminders.update(
        second.id, at(9), "el reciclaje", repeat=WEEKLY, days=WORKDAYS, kind=REMINDER,
        skip_holidays=True,
    )
    parts["timer"].fire(str(second.id))

    line = "🏖 Hoy es feriado: tampoco suena «el reciclaje»"
    assert parts["told"] == [(OWNER, line), (OTHER, line)]


def test_the_summary_keeps_the_history_and_the_moving_on(parts):
    reminders = parts["build"]()
    first = plan(reminders, at(7), "el colegio")
    second = plan(reminders, at(9), "la basura")

    parts["timer"].fire(str(first.id))
    parts["timer"].fire(str(second.id))

    entries = HistoryStore(parts["path"]).between(*DAY)
    assert sorted(entry.job_id for entry in entries) == [first.id, second.id]
    assert {entry.closed for entry in entries} == {HOLIDAY}
    assert reminders.store.get(first.id).when == at(7) + timedelta(days=1)
    assert reminders.store.get(second.id).when == at(9) + timedelta(days=1)


class SlowMarks(Marks):
    """Marcas reales que tardan en leer, para que dos disparos se crucen."""

    def get(self, key):
        value = super().get(key)
        time.sleep(0.05)
        return value


def test_two_firing_at_once_send_one_summary(parts):
    reminders = parts["build"](marks=SlowMarks(parts["path"]))
    jobs = [plan(reminders, at(7), "el colegio"), plan(reminders, at(7), "la basura")]
    start = threading.Barrier(len(jobs))

    def fire(job):
        start.wait()
        reminders._fire(job.id)

    threads = [threading.Thread(target=fire, args=(job,)) for job in jobs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [chat for chat, _ in parts["told"]] == [OWNER, OTHER]


class BrokenMarks:
    def get(self, key):
        raise RuntimeError("la base no contesta")

    def set(self, key, moment):
        raise RuntimeError("la base no contesta")

    def clear(self, key):
        raise RuntimeError("la base no contesta")


def test_broken_marks_fall_back_to_one_line_per_skip(parts):
    reminders = parts["build"](marks=BrokenMarks())
    first = plan(reminders, at(7), "el colegio")
    second = plan(reminders, at(9), "la basura")

    parts["timer"].fire(str(first.id))
    parts["timer"].fire(str(second.id))

    assert parts["told"] == [
        (OWNER, f"🏖 Feriado ({NAME}): hoy no suena «el colegio»"),
        (OTHER, f"🏖 Feriado ({NAME}): hoy no suena «el colegio»"),
        (OWNER, f"🏖 Feriado ({NAME}): hoy no suena «la basura»"),
        (OTHER, f"🏖 Feriado ({NAME}): hoy no suena «la basura»"),
    ]


def test_two_missed_on_a_holiday_after_a_restart_are_told_once(parts):
    reminders = parts["build"]()
    plan(reminders, at(7), "el colegio")
    plan(reminders, at(8), "la basura")

    reminders.start(now=at(12))

    expected = (
        f"🏖 Hoy es feriado ({NAME}), no suenan:\n• 07:00 «el colegio»\n• 08:00 «la basura»"
    )
    assert parts["told"] == [(OWNER, expected), (OTHER, expected)]


def test_one_skip_in_a_chat_is_singular_and_two_are_plural(parts):
    reminders = parts["build"]()
    cin = parts["people"]["cin"]
    mine = plan(reminders, at(7), "el colegio", assignee=PERSON, assignee_id=cin.id)
    plan(reminders, at(8), "la basura")

    parts["timer"].fire(str(mine.id))

    assert parts["told"] == [
        (OWNER, f"🏖 Hoy es feriado ({NAME}), no suenan:\n"
                "• 07:00 «el colegio»\n• 08:00 «la basura»"),
        (OTHER, f"🏖 Hoy es feriado ({NAME}), no suena:\n• 08:00 «la basura»"),
    ]

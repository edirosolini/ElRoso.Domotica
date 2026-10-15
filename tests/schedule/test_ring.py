"""Una alarma suena cada minuto hasta que alguien la apague, con tope."""

from datetime import datetime, timedelta

import pytest

from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.history import CANCEL, OFF, HistoryStore
from homeauto.schedule.reminders import (
    RING_DELAY,
    RING_LIMIT,
    RING_WRITE_EVERY,
    Reminders,
)
from homeauto.schedule.ringing import RingingStore
from homeauto.schedule.store import DAILY, REMINDER, Store

OWNER = 42
OTHER = 99
NOW = datetime(2026, 10, 15, 6, 59)
SOON = NOW + timedelta(minutes=1)


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


class Announcer:
    """Anota cada anuncio y tarda lo que se le pida, como un parlante de verdad."""

    def __init__(self, clock, takes=timedelta(0)):
        self.clock = clock
        self.takes = takes
        self.calls = []
        self.stopped = []
        self.devices = []
        self.fail = None
        # Lo que pasa mientras suena, como un toque en el botón.
        self.meanwhile = None

    def __call__(self, job, rings=0, write=True):
        self.calls.append((job.id, job.message, rings, write))
        self.devices.append(job.devices)
        self.clock.now += self.takes
        if self.meanwhile:
            self.meanwhile(job)
        if self.fail:
            raise self.fail

    def stop(self, devices):
        self.stopped.append(list(devices))


def ring_key(job_id):
    return f"ring:{job_id}"


@pytest.fixture
def parts(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    clock = Clock(NOW)
    told = []
    announcer = Announcer(clock)

    def notify(chat_id, text, actions=()):
        told.append((chat_id, text, actions))

    def build(chat_ids=(OWNER, OTHER)):
        return Reminders(
            store=Store(path),
            timer=timer,
            announce=announcer,
            fired=FiredStore(path),
            awaiting=AwaitingStore(path),
            history=HistoryStore(path),
            ringing=RingingStore(path),
            stop_audio=announcer.stop,
            notify=notify,
            clock=clock,
            chat_ids=chat_ids,
        )

    return {
        "build": build,
        "timer": timer,
        "clock": clock,
        "told": told,
        "announcer": announcer,
        "path": path,
    }


def fire(parts, reminders, **kwargs):
    job = reminders.add(OWNER, SOON, kwargs.pop("message", "arriba"), **kwargs)
    parts["clock"].now = SOON
    parts["timer"].fire(str(job.id))
    return job


def ring(parts, job_id):
    when, action = parts["timer"].armed.pop(ring_key(job_id))
    parts["clock"].now = when
    action()


def history(parts):
    return HistoryStore(parts["path"]).between(NOW, NOW + timedelta(days=2))


# --- cuándo ------------------------------------------------------------------


def test_an_alarm_that_rang_arms_its_repetition_a_minute_after_it_ended(parts):
    parts["announcer"].takes = timedelta(seconds=20)
    job = fire(parts, parts["build"]())

    assert parts["timer"].armed[ring_key(job.id)][0] == SOON + timedelta(seconds=20) + RING_DELAY


def test_a_reminder_never_rings_again(parts):
    job = fire(parts, parts["build"](), kind=REMINDER)

    assert ring_key(job.id) not in parts["timer"].armed


def test_each_repetition_is_a_minute_after_the_last_one_ended(parts):
    parts["announcer"].takes = timedelta(seconds=30)
    job = fire(parts, parts["build"]())

    ring(parts, job.id)

    assert parts["timer"].armed[ring_key(job.id)][0] == parts["clock"].now + RING_DELAY


def test_the_repetition_key_does_not_clash_with_the_daily_rearm_nor_the_nag(parts):
    job = fire(parts, parts["build"](), repeat=DAILY)

    assert str(job.id) in parts["timer"].armed
    assert ring_key(job.id) in parts["timer"].armed
    assert ring_key(job.id) != f"nag:{job.id}"


def test_each_repetition_goes_louder(parts):
    job = fire(parts, parts["build"]())
    ring(parts, job.id)
    ring(parts, job.id)
    ring(parts, job.id)

    assert [rings for *_, rings, _ in parts["announcer"].calls] == [0, 1, 2, 3]


def test_it_stops_at_the_limit_and_says_nobody_turned_it_off(parts):
    job = fire(parts, parts["build"]())

    while ring_key(job.id) in parts["timer"].armed:
        ring(parts, job.id)

    assert parts["clock"].now == SOON + RING_LIMIT
    rang = [call for call in parts["announcer"].calls if call[2]]
    assert len(rang) == int(RING_LIMIT / RING_DELAY) - 1
    stopped = [text for _, text, _ in parts["told"] if "Dejé de sonar" in text]
    assert stopped == ["⏰ Dejé de sonar: «arriba», nadie la apagó"] * 2
    assert RingingStore(parts["path"]).get(job.id) is None


def test_the_chat_hears_about_it_every_five_repetitions(parts):
    job = fire(parts, parts["build"]())
    for _ in range(10):
        ring(parts, job.id)

    writes = [rings for _, _, rings, write in parts["announcer"].calls if rings and write]
    assert writes == [RING_WRITE_EVERY, 2 * RING_WRITE_EVERY]


def test_every_repetition_counts_in_the_history(parts):
    job = fire(parts, parts["build"]())
    ring(parts, job.id)
    ring(parts, job.id)

    [entry] = history(parts)
    assert entry.nags == 2


# --- sin que nada la frene ---------------------------------------------------


def test_a_once_alarm_removed_from_the_jobs_keeps_ringing(parts):
    reminders = parts["build"]()
    job = fire(parts, reminders, message="arriba", device="cocina")

    assert Store(parts["path"]).get(job.id) is None
    ring(parts, job.id)

    job_id, message, rings, _ = parts["announcer"].calls[-1]
    assert (job_id, message, rings) == (job.id, "arriba", 1)


def test_a_repetition_keeps_the_devices_of_the_alarm(parts):
    job = fire(parts, parts["build"](), device="cocina,comedor")

    ring(parts, job.id)

    assert parts["announcer"].devices == [["cocina", "comedor"], ["cocina", "comedor"]]


def test_a_failed_announcement_does_not_stop_the_repetition(parts):
    job = fire(parts, parts["build"]())
    parts["announcer"].fail = RuntimeError("parlante apagado")

    ring(parts, job.id)

    assert ring_key(job.id) in parts["timer"].armed


def test_the_snooze_is_remembered_only_once(parts):
    job = fire(parts, parts["build"]())
    first = FiredStore(parts["path"]).last(OWNER).at

    ring(parts, job.id)

    assert FiredStore(parts["path"]).last(OWNER).at == first


def test_editing_from_the_screen_leaves_the_repetition_alone(parts):
    reminders = parts["build"]()
    job = fire(parts, reminders, repeat=DAILY)
    when = parts["timer"].armed[ring_key(job.id)][0]

    reminders.update(job.id, SOON + timedelta(days=1, hours=1), "arriba ya", repeat=DAILY)

    assert parts["timer"].armed[ring_key(job.id)][0] == when
    assert RingingStore(parts["path"]).get(job.id) is not None


# --- apagarla ----------------------------------------------------------------


def test_turning_it_off_stops_everything_and_tells_the_others(parts):
    reminders = parts["build"]()
    job = fire(parts, reminders, device="cocina")
    ring(parts, job.id)

    assert reminders.silence(OTHER, job.id, "Ana") == "arriba"

    assert ring_key(job.id) not in parts["timer"].armed
    assert RingingStore(parts["path"]).get(job.id) is None
    assert parts["announcer"].stopped == [["cocina"]]
    assert FiredStore(parts["path"]).last(OWNER) is None
    assert FiredStore(parts["path"]).last(OTHER) is None
    [entry] = history(parts)
    assert (entry.closed, entry.done_by) == (OFF, "Ana")
    told = [(chat, text) for chat, text, _ in parts["told"] if "apagó" in text]
    assert told == [(OWNER, "🔕 Ana apagó la alarma: «arriba»")]


def test_turning_it_off_twice_says_it_already_was(parts):
    reminders = parts["build"]()
    job = fire(parts, reminders)
    reminders.silence(OWNER, job.id, "Eze")

    assert reminders.silence(OTHER, job.id, "Ana") is None
    assert parts["announcer"].stopped == [[]]


def test_turning_one_off_does_not_forget_another_that_rang_later(parts):
    reminders = parts["build"]()
    first = fire(parts, reminders, message="arriba")
    second = reminders.add(OWNER, SOON + timedelta(minutes=2), "colegio")
    parts["clock"].now = SOON + timedelta(minutes=2)
    parts["timer"].fire(str(second.id))

    reminders.silence(OWNER, first.id, "Eze")

    assert FiredStore(parts["path"]).last(OWNER).message == "colegio"
    assert ring_key(second.id) in parts["timer"].armed


def test_a_repetition_already_on_its_way_after_turning_off_stays_quiet(parts):
    reminders = parts["build"]()
    job = fire(parts, reminders)
    _, action = parts["timer"].armed[ring_key(job.id)]
    reminders.silence(OWNER, job.id, "Eze")
    calls = len(parts["announcer"].calls)

    action()

    assert len(parts["announcer"].calls) == calls
    assert ring_key(job.id) not in parts["timer"].armed


def test_turning_it_off_while_it_speaks_does_not_rearm_it(parts):
    reminders = parts["build"]()
    parts["announcer"].meanwhile = lambda job: reminders.silence(OWNER, job.id, "Eze")
    job = fire(parts, reminders)

    assert ring_key(job.id) not in parts["timer"].armed


@pytest.mark.parametrize("how", ["snooze", "cancel", "discard"])
def test_snoozing_cancelling_or_discarding_stops_the_repetition(parts, how):
    reminders = parts["build"]()
    job = fire(parts, reminders, repeat=DAILY)

    if how == "snooze":
        assert reminders.snooze(OWNER, timedelta(minutes=10)) is not None
    elif how == "cancel":
        assert reminders.cancel(OWNER, job.id)
    else:
        assert reminders.discard(OTHER, job.id, "Ana") is not None

    assert ring_key(job.id) not in parts["timer"].armed
    assert RingingStore(parts["path"]).get(job.id) is None


def test_a_snoozed_alarm_rings_again_too(parts):
    reminders = parts["build"]()
    fire(parts, reminders)
    snoozed = reminders.snooze(OWNER, timedelta(minutes=10))
    parts["clock"].now = snoozed.when
    parts["timer"].fire(str(snoozed.id))

    assert ring_key(snoozed.id) in parts["timer"].armed


# --- tras un reinicio --------------------------------------------------------


def test_a_late_repetition_rings_once_and_resumes_the_pace(parts):
    job = fire(parts, parts["build"]())
    when, _ = parts["timer"].armed[ring_key(job.id)]
    parts["timer"].armed.clear()
    parts["clock"].now = when + timedelta(minutes=4)

    parts["build"]().start(now=parts["clock"].now)

    assert [rings for *_, rings, _ in parts["announcer"].calls] == [0, 1]
    assert parts["timer"].armed[ring_key(job.id)][0] == parts["clock"].now + RING_DELAY


def test_a_repetition_still_ahead_is_rearmed_where_it_was(parts):
    job = fire(parts, parts["build"]())
    when, _ = parts["timer"].armed[ring_key(job.id)]
    parts["timer"].armed.clear()

    parts["build"]().start(now=parts["clock"].now)

    assert parts["timer"].armed[ring_key(job.id)][0] == when
    assert len(parts["announcer"].calls) == 1


def test_one_past_the_limit_is_closed_without_ringing(parts):
    job = fire(parts, parts["build"]())
    parts["timer"].armed.clear()
    parts["clock"].now = SOON + RING_LIMIT + timedelta(minutes=5)

    parts["build"]().start(now=parts["clock"].now)

    assert len(parts["announcer"].calls) == 1
    assert ring_key(job.id) not in parts["timer"].armed
    assert RingingStore(parts["path"]).get(job.id) is None


def test_without_a_ringing_store_an_alarm_rings_once_as_before(parts):
    path = parts["path"]
    reminders = Reminders(
        store=Store(path),
        timer=parts["timer"],
        announce=parts["announcer"],
        clock=parts["clock"],
    )
    job = fire(parts, reminders)

    assert ring_key(job.id) not in parts["timer"].armed


@pytest.mark.parametrize("how", ["cancel", "discard"])
def test_cancelling_or_discarding_while_it_rings_closes_its_history_as_cancelled(parts, how):
    reminders = parts["build"]()
    job = fire(parts, reminders, repeat=DAILY)
    ring(parts, job.id)

    if how == "cancel":
        reminders.cancel(OWNER, job.id)
    else:
        reminders.discard(OTHER, job.id, "Ana")

    [entry] = history(parts)
    assert entry.closed == CANCEL
    assert entry.closed_at == parts["clock"].now


def test_reaching_the_limit_leaves_its_history_open(parts):
    job = fire(parts, parts["build"]())

    while ring_key(job.id) in parts["timer"].armed:
        ring(parts, job.id)

    [entry] = history(parts)
    assert entry.closed is None

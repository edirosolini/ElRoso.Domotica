"""El depurador: qué propone borrar, qué no toca nunca y qué borra al confirmar."""

from datetime import datetime, timedelta

import pytest

from homeauto.cleanup import (
    GONE_DEVICE,
    IGNORED,
    IGNORED_IN_A_ROW,
    JOBS,
    NOT_A_SCREEN,
    OUTSIDER,
    OVERDUE,
    PLAN_TTL,
    STALE_ONCE,
    TELE_UNSEEN,
    TELES,
    UNSEEN,
    Cleaner,
    job_reasons,
    tele_reason,
)
from homeauto.schedule.awaiting import KEEP, AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.history import DONE, OFF, SNOOZE, HistoryStore
from homeauto.schedule.reminders import SNOOZE_WINDOW, Reminders
from homeauto.schedule.ringing import RingingStore
from homeauto.schedule.store import ALARM, DAILY, ONCE, REMINDER, Job, Store
from homeauto.screen import ScreenStore
from homeauto.tele import Tele, TeleLink, TeleStore
from tests.conftest import NEST_UUID, make_config

OWNER = 42
OTHER = 77
STRANGER = 99
NOW = datetime(2026, 10, 21, 12, 0)


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


class RecordingTimer:
    def __init__(self):
        self.armed = {}
        self.unscheduled = []

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.unscheduled.append(key)
        self.armed.pop(key, None)


class Tokens:
    """Tokens previsibles, uno por vista previa."""

    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1
        return f"t{self.count}"


@pytest.fixture
def house(tmp_path):
    db = tmp_path / "jobs.db"
    clock = Clock()
    timer = RecordingTimer()
    store = Store(db)
    history = HistoryStore(db)
    fired = FiredStore(db)
    awaiting = AwaitingStore(db)
    ringing = RingingStore(db)
    screens = ScreenStore(db)
    link = TeleLink(TeleStore(db), clock=clock)
    reminders = Reminders(
        store=store, timer=timer, announce=lambda job: None, fired=fired, awaiting=awaiting,
        history=history, ringing=ringing, clock=clock,
    )
    config = make_config(
        allowed=(OWNER, OTHER),
        devices={"parlante": NEST_UUID, "comedor": NEST_UUID},
        alert_chat_ids=frozenset({OWNER}),
        screen_devices=("comedor", "recamara"),
    )
    cleaner = Cleaner(
        config=config, reminders=reminders, history=history, fired=fired, awaiting=awaiting,
        ringing=ringing, screens=screens, tele=link, clock=clock, token=Tokens(),
    )
    return {
        "cleaner": cleaner, "clock": clock, "timer": timer, "store": store,
        "history": history, "fired": fired, "awaiting": awaiting, "ringing": ringing,
        "screens": screens, "link": link, "reminders": reminders, "db": db,
    }


def old_tele(house, alias, days=8):
    """Una tele que latió por última vez hace `days` días."""
    house["link"].store.save(
        Tele(alias, "0.1", 1, ("play",), NOW - timedelta(days=days), "192.168.68.30")
    )


def ignored_rows(house, job_id, count=IGNORED_IN_A_ROW, closed=None):
    """`count` filas de historial de días anteriores, sin cerrar o cerradas como se pida."""
    history = house["history"]
    for day in range(count, 0, -1):
        history.record(job_id, OWNER, REMINDER, DAILY, "la pastilla", NOW - timedelta(days=day))
        if closed == DONE:
            history.mark_done(job_id, NOW - timedelta(days=day), "Cin")
        elif closed == OFF:
            history.mark_off(job_id, NOW - timedelta(days=day), "Cin")
        elif closed == SNOOZE:
            history.mark_closed(job_id, SNOOZE, NOW - timedelta(days=day))


def daily(house, chat_id=OWNER, message="la pastilla", device=None, kind=REMINDER):
    return house["reminders"].add(
        chat_id, NOW + timedelta(hours=2), message, repeat=DAILY, device=device, kind=kind
    )


def proposed_jobs(house):
    return house["cleaner"].preview(OWNER, JOBS).jobs


def proposed_teles(house):
    return house["cleaner"].preview(OWNER, TELES).teles


# --- criterios puros ---


def test_a_tele_outside_the_screens_is_not_a_screen():
    tele = Tele("vieja", "0.1", 1, (), NOW, "")

    assert tele_reason(tele, ("comedor",), NOW) == NOT_A_SCREEN


def test_a_tele_unseen_for_a_week_is_unseen_and_a_recent_one_is_fine():
    seen = Tele("comedor", "0.1", 1, (), NOW - TELE_UNSEEN + timedelta(minutes=1), "")
    unseen = Tele("comedor", "0.1", 1, (), NOW - TELE_UNSEEN - timedelta(minutes=1), "")

    assert tele_reason(seen, ("comedor",), NOW) is None
    assert tele_reason(unseen, ("comedor",), NOW) == UNSEEN


def test_the_reasons_of_a_job_are_each_criterion_it_meets():
    job = Job(7, STRANGER, NOW - OVERDUE - timedelta(minutes=1), "x", device="viejo")

    assert job_reasons(job, NOW, {OWNER}, {"parlante"}, []) == (OUTSIDER, GONE_DEVICE, STALE_ONCE)


def test_a_job_on_the_default_device_has_no_device_to_lose():
    job = Job(7, OWNER, NOW + timedelta(hours=1), "x", repeat=DAILY)

    assert job_reasons(job, NOW, {OWNER}, {"parlante"}, []) == ()


def test_a_job_with_one_device_left_still_rings_somewhere():
    job = Job(7, OWNER, NOW + timedelta(hours=1), "x", repeat=DAILY, device="parlante,viejo")

    assert job_reasons(job, NOW, {OWNER}, {"parlante"}, []) == ()


def test_without_an_allowed_list_nobody_is_an_outsider():
    job = Job(7, STRANGER, NOW + timedelta(hours=1), "x", repeat=DAILY)

    assert job_reasons(job, NOW, frozenset(), {"parlante"}, []) == ()


def test_a_one_shot_overdue_by_less_than_a_day_stays():
    job = Job(7, OWNER, NOW - timedelta(hours=12), "x", repeat=ONCE)

    assert job_reasons(job, NOW, {OWNER}, {"parlante"}, []) == ()


# --- teles ---


def test_a_tele_outside_screen_devices_is_proposed(house):
    old_tele(house, "vieja", days=1)

    assert [(c.alias, c.reason) for c in proposed_teles(house)] == [("vieja", NOT_A_SCREEN)]


def test_a_tele_without_a_beat_for_a_week_is_proposed_and_one_from_six_days_ago_is_not(house):
    old_tele(house, "comedor", days=8)
    old_tele(house, "recamara", days=6)

    assert [(c.alias, c.reason) for c in proposed_teles(house)] == [("comedor", UNSEEN)]


def test_a_live_tele_is_never_proposed_even_outside_the_screens(house):
    house["link"].hello("vieja", "0.1", 1, ["play"], "192.168.68.30")

    assert proposed_teles(house) == ()


def test_a_tele_with_a_row_in_screens_is_never_proposed(house):
    old_tele(house, "comedor", days=30)
    house["screens"].show("comedor", 17)

    assert proposed_teles(house) == ()


def test_confirming_forgets_the_teles_shown(house):
    old_tele(house, "vieja")
    preview = house["cleaner"].preview(OWNER, TELES)

    answer = house["cleaner"].confirm(OWNER, preview.token)

    assert "Borré 1 de 1" in answer
    assert house["link"].store.get("vieja") is None


def test_a_tele_that_beat_between_the_preview_and_the_confirm_is_not_deleted(house):
    old_tele(house, "vieja")
    preview = house["cleaner"].preview(OWNER, TELES)
    house["link"].beat("vieja", "192.168.68.30")

    answer = house["cleaner"].confirm(OWNER, preview.token)

    assert "Borré 0 de 1" in answer
    assert house["link"].store.get("vieja") is not None


def test_the_tele_detail_names_each_tele_and_why(house):
    old_tele(house, "vieja", days=1)

    text = house["cleaner"].preview(OWNER, TELES).text

    assert "vieja" in text
    assert "no está en SCREEN_DEVICES" in text


def test_without_the_tele_app_there_are_no_teles_to_clean(house):
    cleaner = Cleaner(
        config=make_config(allowed=(OWNER,)), reminders=house["reminders"], clock=house["clock"],
    )

    preview = cleaner.preview(OWNER, TELES)

    assert preview.token is None
    assert preview.teles == ()


# --- avisos ---


def test_a_job_of_someone_off_the_list_is_proposed(house):
    job = daily(house, chat_id=STRANGER)

    assert [(c.job.id, c.reasons) for c in proposed_jobs(house)] == [(job.id, (OUTSIDER,))]


def test_a_job_on_a_device_that_is_gone_is_proposed(house):
    job = daily(house, device="viejo")

    assert [(c.job.id, c.reasons) for c in proposed_jobs(house)] == [(job.id, (GONE_DEVICE,))]


def test_a_repeating_job_ignored_fourteen_times_in_a_row_is_proposed(house):
    job = daily(house)
    ignored_rows(house, job.id)

    assert [(c.job.id, c.reasons) for c in proposed_jobs(house)] == [(job.id, (IGNORED,))]


def test_thirteen_ignored_times_are_not_enough(house):
    job = daily(house)
    ignored_rows(house, job.id, count=IGNORED_IN_A_ROW - 1)

    assert proposed_jobs(house) == ()


@pytest.mark.parametrize("closed", [DONE, OFF, SNOOZE])
def test_a_job_somebody_answered_is_not_ignored(house, closed):
    job = daily(house)
    ignored_rows(house, job.id, count=IGNORED_IN_A_ROW - 1)
    ignored_rows(house, job.id, count=1, closed=closed)

    assert proposed_jobs(house) == ()


def test_a_one_shot_overdue_by_more_than_a_day_is_proposed(house):
    job = house["store"].add(OWNER, NOW - OVERDUE - timedelta(hours=1), "sacá la pizza")

    assert [(c.job.id, c.reasons) for c in proposed_jobs(house)] == [(job.id, (STALE_ONCE,))]


def test_a_one_shot_in_the_future_is_never_proposed_even_from_a_stranger(house):
    house["reminders"].add(STRANGER, NOW + timedelta(hours=1), "sacá la pizza", device="viejo")

    assert proposed_jobs(house) == ()


def test_a_ringing_alarm_is_never_proposed(house):
    job = daily(house, chat_id=STRANGER, kind=ALARM)
    house["ringing"].remember(job.id, STRANGER, "arriba", None, NOW - timedelta(hours=2))

    assert proposed_jobs(house) == ()


def test_a_job_waiting_for_done_within_the_snooze_window_is_never_proposed(house):
    job = daily(house, chat_id=STRANGER)
    house["awaiting"].remember(job.id, "la pastilla", NOW - timedelta(minutes=10))

    assert proposed_jobs(house) == ()


def test_a_daily_reminder_never_done_is_proposed_although_its_last_wait_is_still_there(house):
    job = daily(house)
    ignored_rows(house, job.id)
    house["awaiting"].remember(job.id, "la pastilla", NOW - timedelta(hours=2))

    assert [(c.job.id, c.reasons) for c in proposed_jobs(house)] == [(job.id, (IGNORED,))]


def test_confirming_a_reminder_with_its_wait_closes_the_wait(house):
    job = daily(house)
    ignored_rows(house, job.id)
    house["awaiting"].remember(job.id, "la pastilla", NOW - timedelta(hours=2))
    preview = house["cleaner"].preview(OWNER, JOBS)

    assert "Borré 1 de 1" in house["cleaner"].confirm(OWNER, preview.token)
    assert house["store"].get(job.id) is None
    assert house["awaiting"].get(job.id) is None
    assert f"nag:{job.id}" in house["timer"].unscheduled


def test_a_job_on_a_screen_is_never_proposed(house):
    job = daily(house, chat_id=STRANGER, kind=ALARM)
    house["screens"].show("comedor", job.id)

    assert proposed_jobs(house) == ()


def test_a_job_that_rang_within_the_snooze_window_is_never_proposed(house):
    job = daily(house, chat_id=STRANGER)
    house["history"].record(job.id, STRANGER, REMINDER, DAILY, "x", NOW - timedelta(minutes=10))

    assert proposed_jobs(house) == ()


def test_a_job_last_fired_within_the_snooze_window_is_never_proposed(house):
    job = daily(house, chat_id=STRANGER)
    house["fired"].remember(OWNER, "x", None, NOW - timedelta(minutes=10), job_id=job.id)

    assert proposed_jobs(house) == ()


def test_the_job_detail_shows_message_repetition_author_and_reason(house):
    job = daily(house, chat_id=STRANGER, message="regar las plantas")

    text = house["cleaner"].preview(OWNER, JOBS).text

    line = next(line for line in text.splitlines() if f"#{job.id}" in line)
    assert "regar las plantas" in line
    assert "todos los días" in line
    assert str(STRANGER) in line
    assert "fuera de la lista" in line


def test_confirming_cancels_each_job_through_reminders(house):
    job = daily(house, chat_id=STRANGER)
    preview = house["cleaner"].preview(OWNER, JOBS)

    answer = house["cleaner"].confirm(OWNER, preview.token)

    assert "Borré 1 de 1" in answer
    assert house["store"].get(job.id) is None
    unscheduled = set(house["timer"].unscheduled)
    assert {str(job.id), f"ring:{job.id}", f"nag:{job.id}"} <= unscheduled


def test_a_job_that_started_ringing_after_the_preview_is_not_deleted(house):
    job = daily(house, chat_id=STRANGER, kind=ALARM)
    preview = house["cleaner"].preview(OWNER, JOBS)
    house["ringing"].remember(job.id, STRANGER, "x", None, NOW)

    answer = house["cleaner"].confirm(OWNER, preview.token)

    assert "Borré 0 de 1" in answer
    assert house["store"].get(job.id) is not None


def test_a_job_added_after_the_preview_is_not_deleted(house):
    preview = house["cleaner"].preview(OWNER, JOBS)
    job = daily(house, chat_id=STRANGER)

    house["cleaner"].confirm(OWNER, preview.token)

    assert house["store"].get(job.id) is not None


# --- restos de lo que sonó ---


def test_an_old_last_fired_and_an_old_wait_are_proposed_and_cleaned(house):
    house["fired"].remember(OWNER, "x", None, NOW - SNOOZE_WINDOW - timedelta(minutes=1))
    house["fired"].remember(OTHER, "x", None, NOW - timedelta(minutes=5))
    house["awaiting"].remember(7, "la pastilla", NOW - KEEP - timedelta(minutes=1))
    house["awaiting"].remember(8, "el colegio", NOW - timedelta(hours=1))

    preview = house["cleaner"].preview(OWNER, JOBS)
    assert preview.fired == (OWNER,)
    assert preview.waits == (7,)

    answer = house["cleaner"].confirm(OWNER, preview.token)

    assert "Borré 2 de 2" in answer
    assert house["fired"].last(OWNER) is None
    assert house["fired"].last(OTHER) is not None
    assert house["awaiting"].get(7) is None
    assert house["awaiting"].get(8) is not None
    assert "nag:7" in house["timer"].unscheduled


def test_a_chat_where_something_rang_again_keeps_its_last_fired(house):
    house["fired"].remember(OWNER, "x", None, NOW - SNOOZE_WINDOW - timedelta(minutes=1))
    preview = house["cleaner"].preview(OWNER, JOBS)
    house["fired"].remember(OWNER, "y", None, NOW)

    house["cleaner"].confirm(OWNER, preview.token)

    assert house["fired"].last(OWNER).message == "y"


# --- el plan ---


def test_the_overview_counts_each_category(house):
    old_tele(house, "vieja")
    daily(house, chat_id=STRANGER)
    house["awaiting"].remember(7, "la pastilla", NOW - KEEP - timedelta(minutes=1))

    overview = house["cleaner"].overview()

    assert (overview.teles, overview.jobs, overview.leftovers) == (1, 1, 1)


def test_nothing_to_clean_gives_no_token(house):
    preview = house["cleaner"].preview(OWNER, JOBS)

    assert preview.token is None
    assert preview.size == 0


def test_an_expired_plan_deletes_nothing(house):
    job = daily(house, chat_id=STRANGER)
    preview = house["cleaner"].preview(OWNER, JOBS)
    house["clock"].advance(seconds=PLAN_TTL.total_seconds() + 1)

    assert house["cleaner"].confirm(OWNER, preview.token) is None
    assert house["store"].get(job.id) is not None


def test_a_plan_is_used_once(house):
    daily(house, chat_id=STRANGER)
    preview = house["cleaner"].preview(OWNER, JOBS)
    house["cleaner"].confirm(OWNER, preview.token)

    assert house["cleaner"].confirm(OWNER, preview.token) is None


def test_a_plan_belongs_to_the_chat_that_asked(house):
    job = daily(house, chat_id=STRANGER)
    preview = house["cleaner"].preview(OWNER, JOBS)

    assert house["cleaner"].confirm(OTHER, preview.token) is None
    assert house["store"].get(job.id) is not None
    assert house["cleaner"].confirm(OWNER, preview.token) is not None


def test_dropping_a_plan_leaves_everything_as_it_was(house):
    job = daily(house, chat_id=STRANGER)
    preview = house["cleaner"].preview(OWNER, JOBS)

    assert house["cleaner"].drop(OWNER, preview.token) is True
    assert house["cleaner"].confirm(OWNER, preview.token) is None
    assert house["store"].get(job.id) is not None


def test_an_old_wait_of_a_proposed_job_is_not_counted_twice(house):
    job = daily(house)
    ignored_rows(house, job.id)
    house["awaiting"].remember(job.id, "la pastilla", NOW - KEEP - timedelta(hours=1))

    preview = house["cleaner"].preview(OWNER, JOBS)

    assert preview.waits == ()
    assert house["cleaner"].overview().leftovers == 0
    assert "Borré 1 de 1" in house["cleaner"].confirm(OWNER, preview.token)
    assert house["awaiting"].get(job.id) is None

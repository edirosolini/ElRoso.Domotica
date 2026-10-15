"""Silencio a pedido: callar un rato sin tocar el horario de descanso."""

from datetime import datetime, timedelta

import pytest

from homeauto.quiet import Hush, HushStore, QuietHours

HOURS = QuietHours.parse("23:00", "07:00")
NOON = datetime(2026, 8, 31, 12, 0)


@pytest.fixture
def hush(tmp_path):
    moment = [NOON]
    silence = Hush(hours=HOURS, store=HushStore(tmp_path / "jobs.db"), clock=lambda: moment[0])
    silence.now = moment  # el test mueve el reloj
    return silence


def test_nothing_asked_means_the_usual_hours(hush):
    assert hush.is_quiet(NOON) is False
    assert hush.is_quiet(datetime(2026, 8, 31, 23, 30)) is True


def test_asking_for_silence_shuts_the_house_up(hush):
    hush.start(timedelta(hours=2))

    assert hush.is_quiet(NOON) is True


def test_the_silence_says_when_it_ends(hush):
    assert hush.start(timedelta(hours=2)) == datetime(2026, 8, 31, 14, 0)
    assert hush.until() == datetime(2026, 8, 31, 14, 0)


def test_once_the_time_is_up_the_house_talks_again(hush):
    hush.start(timedelta(hours=2))

    hush.now[0] = datetime(2026, 8, 31, 14, 1)

    assert hush.is_quiet(hush.now[0]) is False
    assert hush.until() is None


def test_it_can_be_cut_short(hush):
    hush.start(timedelta(hours=2))

    assert hush.stop() is True
    assert hush.is_quiet(NOON) is False


def test_stopping_a_silence_nobody_asked_for_says_so(hush):
    assert hush.stop() is False


def test_the_resting_hours_still_win_after_the_silence_ends(hush):
    hush.start(timedelta(minutes=10))
    hush.now[0] = datetime(2026, 9, 1, 2, 0)

    assert hush.is_quiet(hush.now[0]) is True


def test_the_label_explains_which_rule_is_talking(hush):
    assert hush.label == HOURS.label

    hush.start(timedelta(hours=2))

    assert "14:00" in hush.label
    assert "pedido" in hush.label


def test_the_silence_survives_a_restart(tmp_path):
    store = lambda: HushStore(tmp_path / "jobs.db")
    Hush(hours=HOURS, store=store(), clock=lambda: NOON).start(timedelta(hours=2))

    revived = Hush(hours=HOURS, store=store(), clock=lambda: NOON)

    assert revived.is_quiet(NOON) is True


def test_a_new_silence_replaces_the_one_before(hush):
    hush.start(timedelta(hours=2))
    hush.start(timedelta(minutes=30))

    assert hush.until() == datetime(2026, 8, 31, 12, 30)


# --- modo vacaciones ---------------------------------------------------------

from homeauto.quiet import AwayStore, Vacation  # noqa: E402

BACK = datetime(2026, 9, 25, 0, 0)


@pytest.fixture
def away(tmp_path):
    moment = [NOON]
    path = tmp_path / "jobs.db"
    silence = Hush(
        hours=HOURS, store=HushStore(path), clock=lambda: moment[0], away=AwayStore(path)
    )
    silence.now = moment
    return silence


def test_without_vacations_the_reason_is_the_resting_hours(away):
    assert away.is_away(NOON) is False
    assert away.reason() == f"Horario de descanso ({HOURS.label})"


def test_the_bare_resting_hours_have_the_same_shape():
    assert HOURS.is_away(NOON) is False
    assert HOURS.away_until(NOON) is None
    assert HOURS.reason() == f"Horario de descanso ({HOURS.label})"


def test_on_vacation_the_house_is_quiet_all_day(away):
    away.start_away(BACK)

    assert away.is_away(NOON) is True
    assert away.is_quiet(NOON) is True
    assert away.away_until(NOON) == BACK


def test_the_reason_on_vacation_says_until_when(away):
    away.start_away(BACK)

    assert away.reason() == "De vacaciones hasta el 25/09"


def test_a_return_with_an_hour_says_the_hour(away):
    away.start_away(datetime(2026, 9, 25, 18, 0))

    assert away.reason() == "De vacaciones hasta el 25/09 a las 18:00"


def test_vacations_end_on_their_own_and_clear_the_row(away, tmp_path):
    away.start_away(BACK)

    assert away.is_away(BACK) is False
    assert AwayStore(tmp_path / "jobs.db").until() is None
    assert away.is_quiet(datetime(2026, 9, 25, 12, 0)) is False


def test_vacations_can_be_cut_short(away):
    away.start_away(BACK)

    assert away.stop_away() is True
    assert away.is_away(NOON) is False
    assert away.stop_away() is False


def test_speaking_again_does_not_end_the_vacations(away):
    away.start_away(BACK)
    away.start(timedelta(hours=1))

    assert away.stop() is True
    assert away.is_away(NOON) is True


def test_vacations_survive_a_restart(tmp_path):
    path = tmp_path / "jobs.db"
    Hush(hours=HOURS, store=HushStore(path), clock=lambda: NOON, away=AwayStore(path)).start_away(
        BACK
    )

    revived = Hush(hours=HOURS, store=HushStore(path), clock=lambda: NOON, away=AwayStore(path))

    assert revived.is_away(NOON) is True


def test_without_an_away_store_there_are_no_vacations(hush):
    assert hush.is_away(NOON) is False
    with pytest.raises(RuntimeError):
        hush.start_away(BACK)


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)


def vacation(away, chat_ids=(42, 77)):
    timer = FakeTimer()
    sent = []
    plan = Vacation(
        hush=away,
        timer=timer,
        notify=lambda chat_id, text: sent.append((chat_id, text)),
        chat_ids=chat_ids,
        clock=lambda: away.now[0],
    )
    return plan, timer, sent


def test_starting_vacations_arms_the_end_and_tells_the_others(away):
    plan, timer, sent = vacation(away)

    plan.begin(BACK, 42, "Eze")

    assert away.is_away(NOON) is True
    [(when, _)] = timer.armed.values()
    assert when == BACK
    assert sent == [(77, "🧳 Eze activó vacaciones hasta el 25/09")]


def test_cutting_vacations_disarms_the_end_and_tells_the_others(away):
    plan, timer, sent = vacation(away)
    plan.begin(BACK, 42, "Eze")
    sent.clear()

    assert plan.end(77, "Ana") is True

    assert timer.armed == {}
    assert away.is_away(NOON) is False
    assert sent == [(42, "🧳 Ana cortó las vacaciones")]


def test_cutting_vacations_nobody_started_says_so(away):
    plan, _, sent = vacation(away)

    assert plan.end(42, "Eze") is False
    assert sent == []


def test_the_end_of_the_vacations_is_told_to_everyone(away):
    plan, timer, sent = vacation(away)
    plan.begin(BACK, 42, "Eze")
    sent.clear()
    [(_, finish)] = timer.armed.values()

    away.now[0] = BACK
    finish()

    assert sent == [
        (42, "🧳 Terminó el modo vacaciones, vuelvo a hablar."),
        (77, "🧳 Terminó el modo vacaciones, vuelvo a hablar."),
    ]
    assert away.is_away(BACK) is False


def test_a_restart_rearms_the_end(away):
    away.start_away(BACK)
    plan, timer, sent = vacation(away)

    plan.start()

    [(when, _)] = timer.armed.values()
    assert when == BACK
    assert sent == []


def test_vacations_that_ended_while_down_are_told_at_start(away):
    away.start_away(BACK)
    away.now[0] = datetime(2026, 9, 26, 9, 0)
    plan, timer, sent = vacation(away)

    plan.start()

    assert timer.armed == {}
    assert [text for _, text in sent] == ["🧳 Terminó el modo vacaciones, vuelvo a hablar."] * 2
    assert away.is_away(away.now[0]) is False


def test_without_vacations_the_start_arms_nothing(away):
    plan, timer, sent = vacation(away)

    plan.start()

    assert timer.armed == {} and sent == []


def test_a_broken_chat_does_not_stop_the_others(away):
    timer = FakeTimer()
    sent = []

    def notify(chat_id, text):
        if chat_id == 42:
            raise RuntimeError("caído")
        sent.append(chat_id)

    plan = Vacation(hush=away, timer=timer, notify=notify, chat_ids=(42, 77), clock=lambda: NOON)
    plan.begin(BACK, 99, "Eze")

    assert sent == [77]


def test_starting_vacations_stops_the_alarms_that_are_ringing(away):
    stopped = []
    plan = Vacation(
        hush=away,
        timer=FakeTimer(),
        notify=lambda chat_id, text: None,
        chat_ids=(42,),
        clock=lambda: NOON,
        stop_ringing=lambda: stopped.append(True),
    )

    plan.begin(BACK, 42, "Eze")

    assert stopped == [True]


def test_a_broken_stop_does_not_cost_the_vacations(away):
    def broken():
        raise RuntimeError("sqlite")

    plan = Vacation(
        hush=away,
        timer=FakeTimer(),
        notify=lambda chat_id, text: None,
        chat_ids=(42,),
        clock=lambda: NOON,
        stop_ringing=broken,
    )

    plan.begin(BACK, 42, "Eze")

    assert away.is_away(NOON) is True

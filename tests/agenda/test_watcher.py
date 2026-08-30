from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeauto.agenda.ical import CalendarError, Event
from homeauto.agenda.seen import SeenStore
from homeauto.agenda.watcher import EventWatcher

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
NOW = datetime(2026, 8, 30, 9, 0, tzinfo=TZ)


def event(minutes_ahead, summary="Reunión", uid=None):
    start = NOW + timedelta(minutes=minutes_ahead)
    return Event(uid or f"{summary}@t", summary, start, start + timedelta(hours=1), False, "personal")


class FakeCalendar:
    def __init__(self, events=(), boom=None):
        self.events = list(events)
        self.boom = boom

    def between(self, start, end):
        if self.boom:
            raise self.boom
        return [e for e in self.events if start <= e.start < end]


def build(tmp_path, events=(), boom=None, lead=10, now=NOW):
    said = []
    watcher = EventWatcher(
        calendar=FakeCalendar(events, boom),
        announce=said.append,
        seen=SeenStore(tmp_path / "jobs.db"),
        lead_minutes=lead,
        clock=lambda: now,
    )
    return watcher, said


def test_it_warns_about_an_event_about_to_start(tmp_path):
    watcher, said = build(tmp_path, [event(5, "Reunión con el equipo")])

    watcher.check()

    assert len(said) == 1
    assert "Reunión con el equipo" in said[0]
    assert "5 minutos" in said[0]


def test_it_does_not_warn_twice(tmp_path):
    watcher, said = build(tmp_path, [event(5)])

    watcher.check()
    watcher.check()

    assert len(said) == 1


def test_it_ignores_what_is_still_far_away(tmp_path):
    watcher, said = build(tmp_path, [event(45)])

    watcher.check()

    assert said == []


def test_it_does_not_shout_events_that_already_started(tmp_path):
    """Tras un reinicio, lo que ya empezó es ruido, no aviso."""
    watcher, said = build(tmp_path, [event(-15)])

    watcher.check()

    assert said == []


def test_after_a_restart_it_still_remembers(tmp_path):
    watcher, said = build(tmp_path, [event(5)])
    watcher.check()

    again, said_again = build(tmp_path, [event(5)])
    again.check()

    assert len(said) == 1 and said_again == []


def test_two_different_events_both_get_a_warning(tmp_path):
    watcher, said = build(tmp_path, [event(3, "Uno", "a@t"), event(7, "Dos", "b@t")])

    watcher.check()

    assert len(said) == 2


def test_an_event_starting_right_now_is_announced(tmp_path):
    watcher, said = build(tmp_path, [event(0, "Ahora")])

    watcher.check()

    assert len(said) == 1
    assert "ahora" in said[0].lower()


def test_a_calendar_failure_does_not_break_the_loop(tmp_path):
    watcher, said = build(tmp_path, boom=CalendarError("sin red"))

    watcher.check()  # no explota

    assert said == []


def test_a_failing_announcement_is_not_marked_as_done(tmp_path):
    """Si no se pudo avisar, hay que reintentar en la vuelta siguiente."""
    seen = SeenStore(tmp_path / "jobs.db")
    attempts = []

    def announce(text):
        attempts.append(text)
        raise RuntimeError("parlante caído")

    watcher = EventWatcher(
        calendar=FakeCalendar([event(5)]),
        announce=announce,
        seen=seen,
        lead_minutes=10,
        clock=lambda: NOW,
    )

    watcher.check()
    watcher.check()

    assert len(attempts) == 2


def test_the_lead_time_is_respected(tmp_path):
    watcher, said = build(tmp_path, [event(25)], lead=30)

    watcher.check()

    assert len(said) == 1

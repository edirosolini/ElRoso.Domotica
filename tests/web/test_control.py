"""La pantalla de control: lo urgente de ahora y los comandos, sin HTTP."""

from datetime import datetime, time, timedelta

import pytest

from homeauto.bot.commands import offer
from homeauto.people import PeopleStore
from homeauto.quiet import AwayStore, Hush, HushStore, QuietHours
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.ringing import RingingStore
from homeauto.watch.status import Status
from homeauto.web.control import ControlService
from homeauto.web.jobs import ReadOnly, WebError

NOW = datetime(2026, 10, 19, 12, 0)
HOURS = QuietHours(start=time(22, 0), end=time(5, 25))


class StubCommands:
    """Doble de Commands: anota lo pedido y contesta como el de verdad, con botones."""

    def __init__(self, fail=None):
        self.asked = []
        self.fail = fail

    def press(self, chat_id, data, who=""):
        self.asked.append(("press", chat_id, data, who))
        if self.fail:
            raise self.fail
        offer(("Cancelar #7", "cancelar 7"))
        return f"apretado {data}"

    def free_text(self, chat_id, text):
        self.asked.append(("free_text", chat_id, text))
        if self.fail:
            raise self.fail
        return f"Entendí: {text}"


class StubMonitor:
    def __init__(self, states):
        self.states = states

    def snapshot(self):
        return {state.name: state for state in self.states}


def status(name, up, alerted=False, acked_by="", detail="HTTP 503 en http://10.0.0.9/secreto"):
    return Status(name, up, 0 if up else 2, alerted, detail, NOW - timedelta(minutes=5),
                  acked_by=acked_by)


@pytest.fixture
def db(tmp_path):
    return tmp_path / "jobs.db"


@pytest.fixture
def commands():
    return StubCommands()


def make(db, commands=None, monitor=None, chat_ids=(42, 77), alerts=(42,), clock=lambda: NOW):
    people = PeopleStore(db)
    people.remember(42, "Eze")
    return ControlService(
        commands=commands or StubCommands(),
        ringing=RingingStore(db),
        awaiting=AwaitingStore(db),
        fired=FiredStore(db),
        monitor=monitor,
        quiet=Hush(hours=HOURS, store=HushStore(db), clock=clock, away=AwayStore(db)),
        people=people,
        alert_recipients=frozenset(alerts),
        chat_ids=frozenset(chat_ids),
        clock=clock,
    )


# --- lo de ahora ---


def test_a_ringing_alarm_comes_with_its_off_button(db):
    control = make(db)
    control.ringing.remember(17, 42, "arriba", None, NOW - timedelta(minutes=2))

    live = control.live(77)

    assert live["ringing"] == [{
        "job_id": 17, "message": "arriba", "since": "2026-10-19T11:58:00", "rings": 0,
        "actions": [{"label": "🔕 Apagar", "data": "callar 17"}],
    }]


def test_what_waits_its_done_comes_with_its_button(db):
    control = make(db)
    control.awaiting.remember(9, "pastilla", NOW - timedelta(minutes=10))

    [waiting] = control.live(42)["awaiting"]

    assert waiting["job_id"] == 9 and waiting["message"] == "pastilla"
    assert waiting["actions"] == [{"label": "✅ Hecho", "data": "hecho 9"}]


def test_what_waited_longer_than_a_day_is_not_shown(db):
    control = make(db)
    control.awaiting.remember(9, "pastilla", NOW - timedelta(days=2))

    assert control.live(42)["awaiting"] == []


def test_the_last_thing_that_rang_in_that_chat_can_be_postponed(db):
    control = make(db)
    control.fired.remember(42, "arriba", None, NOW - timedelta(minutes=5), job_id=17)

    snooze = control.live(42)["snooze"]

    assert snooze["message"] == "arriba" and snooze["job_id"] == 17
    assert snooze["actions"] == [
        {"label": "Posponer 10 min", "data": "posponer 10m"},
        {"label": "Posponer 30 min", "data": "posponer 30m"},
    ]
    assert control.live(77)["snooze"] is None


def test_what_rang_more_than_half_an_hour_ago_cannot_be_postponed(db):
    control = make(db)
    control.fired.remember(42, "arriba", None, NOW - timedelta(minutes=31))

    assert control.live(42)["snooze"] is None


def test_an_unconfirmed_outage_offers_confirm_only_to_an_alert_chat(db):
    monitor = StubMonitor([
        status("vps", False, alerted=True),
        status("nas", False, alerted=True, acked_by="Eze"),
        status("router", False, alerted=False),
        status("web", True),
    ])
    control = make(db, monitor=monitor)

    alert = control.live(42)["outages"]
    other = control.live(77)["outages"]

    assert [outage["name"] for outage in alert] == ["vps"]
    assert alert[0]["actions"] == [{"label": "✅ Confirmar", "data": "confirmar vps"}]
    assert other[0]["actions"] == []


def test_the_status_says_what_is_up_without_the_details(db):
    monitor = StubMonitor([status("web", True), status("vps", False, alerted=True)])
    live = make(db, monitor=monitor).live(42)

    assert live["status"] == [{"name": "vps", "up": False}, {"name": "web", "up": True}]
    assert "secreto" not in repr(live) and "10.0.0.9" not in repr(live)


def test_without_a_monitor_there_is_nothing_down(db):
    live = make(db).live(42)

    assert live["outages"] == [] and live["status"] == []


def test_the_quiet_offers_to_hush_when_the_house_talks(db):
    quiet = make(db).live(42)["quiet"]

    assert quiet == {"quiet": False, "reason": "", "hush_until": None, "away_until": None,
                     "actions": [{"label": "Silenciar 1 h", "data": "silencio 1h"}]}


def test_a_hush_asked_by_hand_offers_to_talk_again(db):
    control = make(db)
    control.quiet.start(timedelta(hours=1))

    quiet = control.live(42)["quiet"]

    assert quiet["quiet"] is True
    assert quiet["hush_until"] == "2026-10-19T13:00:00"
    assert quiet["reason"].startswith("Horario de descanso")
    assert quiet["actions"] == [{"label": "Hablar ya", "data": "hablar"}]


def test_the_vacations_offer_to_end_them(db):
    control = make(db)
    control.quiet.start_away(datetime(2026, 10, 25))

    quiet = control.live(42)["quiet"]

    assert quiet["away_until"] == "2026-10-25T00:00:00"
    assert quiet["reason"] == "De vacaciones hasta el 25/10"
    assert quiet["actions"] == [{"label": "Cortar vacaciones", "data": "vacaciones off"}]


def test_live_carries_the_house_hour(db):
    assert make(db).live(42)["now"] == "2026-10-19T12:00:00"


@pytest.mark.parametrize("chat_id", [99, None, "42", True])
def test_live_for_a_chat_outside_the_house_is_refused(db, chat_id):
    with pytest.raises(ReadOnly):
        make(db).live(chat_id)


def test_without_allowed_chats_there_is_no_control(db):
    with pytest.raises(ReadOnly):
        make(db, chat_ids=()).live(42)


# --- los comandos ---


def test_a_button_runs_through_press_with_who_from_the_screen(db, commands):
    control = make(db, commands=commands)

    answer = control.run({"chat_id": 42, "data": "callar 17"})

    assert commands.asked == [("press", 42, "callar 17", "Eze (pantalla)")]
    assert answer == {"text": "apretado callar 17",
                      "actions": [{"label": "Cancelar #7", "data": "cancelar 7"}]}


def test_a_chat_without_a_name_is_named_by_its_id(db, commands):
    make(db, commands=commands).run({"chat_id": 77, "data": "clima"})

    assert commands.asked[0][3] == "Chat 77 (pantalla)"


def test_free_text_goes_through_the_router(db, commands):
    answer = make(db, commands=commands).run({"chat_id": 42, "text": "  dame el clima "})

    assert commands.asked == [("free_text", 42, "dame el clima")]
    assert answer["text"] == "Entendí: dame el clima"


def test_a_command_that_breaks_is_answered_not_silenced(db):
    control = make(db, commands=StubCommands(fail=RuntimeError("Address already in use")))

    answer = control.run({"chat_id": 42, "data": "decir hola"})

    assert answer == {"text": "🔴 No pude procesar la solicitud: Address already in use",
                      "actions": []}


@pytest.mark.parametrize("chat_id", [99, None, "42", True])
def test_a_command_from_a_chat_outside_the_house_is_refused(db, commands, chat_id):
    with pytest.raises(ReadOnly):
        make(db, commands=commands).run({"chat_id": chat_id, "data": "clima"})
    assert commands.asked == []


def test_without_allowed_chats_no_command_runs(db, commands):
    with pytest.raises(ReadOnly):
        make(db, commands=commands, chat_ids=()).run({"chat_id": 42, "data": "clima"})
    assert commands.asked == []


@pytest.mark.parametrize(
    "payload",
    [
        {"chat_id": 42},
        {"chat_id": 42, "text": ""},
        {"chat_id": 42, "text": "   "},
        {"chat_id": 42, "data": 3},
        {"chat_id": 42, "text": "x" * 501},
        {"chat_id": 42, "data": "x" * 501},
        {"chat_id": 42, "text": "hola", "data": "clima"},
    ],
)
def test_a_command_without_exactly_one_short_text_gets_400(db, commands, payload):
    with pytest.raises(WebError) as caught:
        make(db, commands=commands).run(payload)
    assert caught.value.status == 400
    assert commands.asked == []

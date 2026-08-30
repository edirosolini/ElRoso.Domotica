from datetime import datetime, time
from zoneinfo import ZoneInfo

from homeauto.agenda.ical import CalendarError
from homeauto.bot.commands import Commands
from homeauto.quiet import QuietHours

from tests.conftest import FakeSpeaker, StubRegistry, make_config

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
OWNER = 42
BY_DAY = datetime(2026, 8, 30, 15, 0, tzinfo=TZ)
AT_NIGHT = datetime(2026, 8, 30, 3, 0, tzinfo=TZ)
NIGHT = QuietHours(start=time(23, 0), end=time(7, 0))


class FakeAgenda:
    def __init__(self, text="Hoy tenés 1 cosa. A las 18, cena.", boom=None):
        self.text = text
        self.boom = boom
        self.asked = []

    def spoken(self, when=""):
        self.asked.append(when)
        if self.boom:
            raise self.boom
        return self.text


def build(agenda=None, now=BY_DAY, quiet=None, **speakers):
    speakers = speakers or {"parlante": FakeSpeaker("parlante")}
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        agenda=agenda or FakeAgenda(),
        quiet=quiet,
        clock=lambda: now,
    )
    return commands, speakers


def test_it_says_the_agenda_out_loud():
    cmd, spk = build()

    reply = cmd.agenda_command(OWNER, "")

    assert spk["parlante"].said == ["Hoy tenés 1 cosa. A las 18, cena."]
    assert "cena" in reply


def test_tomorrow_is_passed_through():
    agenda = FakeAgenda()
    cmd, _ = build(agenda=agenda)

    cmd.agenda_command(OWNER, "mañana")

    assert agenda.asked == ["mañana"]


def test_it_can_go_to_another_device():
    parlante, comedor = FakeSpeaker("parlante"), FakeSpeaker("comedor")
    cmd, _ = build(parlante=parlante, comedor=comedor)

    cmd.agenda_command(OWNER, "en comedor")

    assert comedor.said and not parlante.said


def test_the_target_does_not_eat_the_day_word():
    agenda = FakeAgenda()
    parlante, comedor = FakeSpeaker("parlante"), FakeSpeaker("comedor")
    cmd, _ = build(agenda=agenda, parlante=parlante, comedor=comedor)

    cmd.agenda_command(OWNER, "en comedor mañana")

    assert agenda.asked == ["mañana"]
    assert comedor.said


def test_a_word_it_does_not_understand_is_explained():
    cmd, spk = build(agenda=FakeAgenda(boom=ValueError("No entiendo 'el jueves'. Probá con hoy o mañana.")))

    reply = cmd.agenda_command(OWNER, "el jueves")

    assert "No entiendo" in reply
    assert spk["parlante"].said == []


def test_a_calendar_failure_is_explained_and_nothing_is_said():
    cmd, spk = build(agenda=FakeAgenda(boom=CalendarError("no pude bajar el calendario")))

    reply = cmd.agenda_command(OWNER, "")

    assert "no pude bajar el calendario" in reply
    assert spk["parlante"].said == []


def test_at_night_it_only_writes():
    cmd, spk = build(now=AT_NIGHT, quiet=NIGHT)

    reply = cmd.agenda_command(OWNER, "")

    assert spk["parlante"].said == []
    assert "cena" in reply
    assert "descanso" in reply.lower()


def test_without_a_calendar_configured_it_says_so():
    commands = Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
    )

    reply = commands.agenda_command(OWNER, "")

    assert "calendario" in reply.lower()


def test_a_stranger_gets_nothing():
    cmd, spk = build()

    cmd.agenda_command(99, "")

    assert spk["parlante"].said == []

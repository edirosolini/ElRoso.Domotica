from datetime import datetime, time

from homeauto.bot.commands import Commands
from homeauto.quiet import QuietHours
from homeauto.schedule.announcer import Announcer
from homeauto.schedule.store import Job

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
NIGHT = QuietHours(start=time(23, 0), end=time(7, 0))
AT_NIGHT = datetime(2026, 8, 30, 3, 0)
BY_DAY = datetime(2026, 8, 30, 15, 0)
JOB = Job(id=7, chat_id=OWNER, when=AT_NIGHT, message="arriba")


def build_commands(now):
    speaker = FakeSpeaker("parlante")
    commands = Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=speaker),
        quiet=NIGHT,
        clock=lambda: now,
    )
    return commands, speaker


def build_announcer(now):
    speaker = FakeSpeaker("parlante")
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda chat_id, text: sent.append((chat_id, text)),
        fallback="parlante",
        quiet=NIGHT,
        clock=lambda: now,
    )
    return announcer, speaker, sent


def test_at_night_an_alarm_only_reaches_telegram():
    announcer, speaker, sent = build_announcer(AT_NIGHT)

    announcer(JOB)

    assert speaker.said == [], "a las 3 de la mañana no se grita"
    assert len(sent) == 1
    assert "arriba" in sent[0][1]


def test_the_chat_is_told_why_it_did_not_sound():
    announcer, _, sent = build_announcer(AT_NIGHT)

    announcer(JOB)

    assert "descanso" in sent[0][1].lower()
    assert "23:00" in sent[0][1]


def test_by_day_the_alarm_sounds_as_usual():
    announcer, speaker, sent = build_announcer(BY_DAY)

    announcer(JOB)

    assert speaker.said == ["arriba"]
    assert len(sent) == 1


def test_at_night_decir_does_not_sound_either():
    commands, speaker = build_commands(AT_NIGHT)

    reply = commands.say(OWNER, "probando")

    assert speaker.said == []
    assert "descanso" in reply.lower()
    assert "23:00" in reply


def test_by_day_decir_sounds():
    commands, speaker = build_commands(BY_DAY)

    commands.say(OWNER, "probando")

    assert speaker.said == ["probando"]


def test_without_quiet_hours_everything_sounds():
    speaker = FakeSpeaker("parlante")
    commands = Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=speaker),
        clock=lambda: AT_NIGHT,
    )

    commands.say(OWNER, "a cualquier hora")

    assert speaker.said == ["a cualquier hora"]

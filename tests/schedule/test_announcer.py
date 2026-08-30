from datetime import datetime

import pytest

from homeauto.schedule.announcer import Announcer
from homeauto.schedule.store import Job
from homeauto.voice.caster import CastError
from homeauto.voice.tts import TtsError

JOB = Job(id=7, chat_id=42, when=datetime(2026, 8, 30, 7, 30), message="arriba")


class FakeSpeaker:
    def __init__(self, fail=None):
        self.said = []
        self.fail = fail

    def say(self, text):
        if self.fail:
            raise self.fail
        self.said.append(text)


def build(fail=None):
    speaker = FakeSpeaker(fail)
    sent = []
    return Announcer(speaker=speaker, notify=lambda chat_id, text: sent.append((chat_id, text))), speaker, sent


def test_says_it_out_loud():
    announcer, speaker, _ = build()

    announcer(JOB)

    assert speaker.said == ["arriba"]


def test_also_writes_to_the_chat():
    announcer, _, sent = build()

    announcer(JOB)

    assert len(sent) == 1
    chat_id, text = sent[0]
    assert chat_id == 42
    assert "arriba" in text


@pytest.mark.parametrize("failure", [CastError("parlante apagado"), TtsError("piper falló")])
def test_chat_still_gets_it_when_the_speaker_fails(failure):
    announcer, _, sent = build(fail=failure)

    announcer(JOB)

    assert len(sent) == 1, "si no suena, el aviso tiene que llegar igual al teléfono"
    _, text = sent[0]
    assert "arriba" in text


def test_the_chat_is_told_that_it_did_not_sound():
    announcer, _, sent = build(fail=CastError("parlante apagado"))

    announcer(JOB)

    _, text = sent[0]
    assert "parlante apagado" in text
    assert "no pude" in text.lower()


def test_a_broken_chat_does_not_stop_the_voice():
    speaker = FakeSpeaker()

    def notify(chat_id, text):
        raise RuntimeError("telegram caído")

    Announcer(speaker=speaker, notify=notify)(JOB)

    assert speaker.said == ["arriba"], "el parlante ya habló: un fallo de Telegram no lo deshace"


def test_daily_jobs_are_marked_as_such():
    daily = Job(id=8, chat_id=42, when=JOB.when, message="arriba", repeat="daily")
    announcer, _, sent = build()

    announcer(daily)

    _, text = sent[0]
    assert "todos los días" in text.lower()

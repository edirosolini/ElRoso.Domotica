"""`/calcular`: la cuenta se resuelve acá y solo suena si la piden."""

from datetime import datetime, time

from homeauto.bot.commands import Commands
from homeauto.quiet import QuietHours

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42


def build(quiet=None, clock=None, **speakers):
    speakers = speakers or {"parlante": FakeSpeaker("parlante")}
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        quiet=quiet,
        clock=clock or datetime.now,
    )
    return commands, speakers


def test_it_answers_in_writing_without_touching_the_speaker():
    cmd, spk = build()

    reply = cmd.calculate(OWNER, "15 por 4")

    assert "60" in reply
    assert spk["parlante"].said == [], "el parlante se pide, no es el default"


def test_it_speaks_the_result_in_words_when_it_is_asked_for():
    cmd, spk = build()

    reply = cmd.calculate(OWNER, "15 por 4 por el parlante")

    assert spk["parlante"].said == ["Son sesenta."]
    assert "60" in reply, "lo escrito conserva la cifra"


def test_a_conversion_works_the_same_way():
    cmd, spk = build()

    reply = cmd.calculate(OWNER, "20 grados en fahrenheit por el parlante")

    assert "68" in reply
    assert "sesenta y ocho" in spk["parlante"].said[0]


def test_it_goes_to_the_device_you_asked_for():
    parlante, comedor = FakeSpeaker("parlante"), FakeSpeaker("comedor")
    cmd, _ = build(parlante=parlante, comedor=comedor)

    cmd.calculate(OWNER, "en comedor 2 más 2 por el parlante")

    assert comedor.said and not parlante.said


def test_without_a_calculation_it_says_how_to_use_it():
    cmd, _ = build()

    assert "/calcular" in cmd.calculate(OWNER, "")


def test_something_that_is_not_a_calculation_is_answered_not_crashed():
    cmd, _ = build()

    reply = cmd.calculate(OWNER, "qué onda")

    assert reply and "🔴" not in reply


def test_dividing_by_zero_is_explained():
    cmd, _ = build()

    assert "cero" in cmd.calculate(OWNER, "5 / 0")


def test_a_number_too_big_to_say_comes_back_written():
    """`verbalize` corta en 999.999: la respuesta no se pierde, cambia de forma."""
    cmd, spk = build()

    reply = cmd.calculate(OWNER, "999999 * 99 por el parlante")

    assert "98.999.901" in reply
    assert spk["parlante"].said == []


def test_during_quiet_hours_it_only_writes():
    cmd, spk = build(
        quiet=QuietHours(start=time(23, 0), end=time(7, 0)),
        clock=lambda: datetime(2026, 9, 22, 3, 0),
    )

    reply = cmd.calculate(OWNER, "15 por 4 por el parlante")

    assert "60" in reply
    assert "descanso" in reply.lower()
    assert spk["parlante"].said == []


def test_a_stranger_gets_nothing():
    cmd, spk = build()

    reply = cmd.calculate(999, "15 por 4")

    assert "lista" in reply.lower()
    assert spk["parlante"].said == []

"""Lo que una persona escribe se dice bien escrito, pero sigue siendo suyo.

🔴 Reemplaza la regla anterior de que `/decir` iba literal. Lo que cambia es la
ortografía, los números y la comida según la hora; las palabras no.
"""

from datetime import datetime

from homeauto.bot.commands import Commands
from homeauto.correct import Corrector

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
NIGHT = datetime(2026, 9, 4, 21, 30)


def build(correct=None):
    speakers = {"parlante": FakeSpeaker("parlante")}
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        correct=correct if correct is not None else (lambda text: text),
        clock=lambda: NIGHT,
    )
    return commands, speakers


def corrector_saying(reply):
    def model(prompt):
        model.prompts.append(prompt)
        return reply
    model.prompts = []
    return Corrector(model, clock=lambda: NIGHT).correct


def test_what_reaches_the_speaker_is_the_corrected_text():
    cmd, spk = build(corrector_saying("Diego, es hora de cenar."))

    cmd.say(OWNER, "Diego es hoa de comer")

    assert spk["parlante"].said == ["Diego, es hora de cenar."]


def test_the_reply_says_it_told_them_and_what_it_said():
    cmd, _ = build(corrector_saying("Diego, es hora de cenar."))

    reply = cmd.say(OWNER, "Diego es hoa de comer")

    assert "Ya le avisé" in reply
    assert "«Diego, es hora de cenar.»" in reply


def test_a_correction_that_invents_words_never_reaches_the_speaker():
    cmd, spk = build(corrector_saying("Diego, la cena está servida en la mesa."))

    cmd.say(OWNER, "Diego es hora de comer")

    assert spk["parlante"].said == ["Diego es hora de comer"]


def test_without_a_key_the_text_goes_as_it_was_typed():
    """`as_written` es el default: sin modelo, nada cambia."""
    from homeauto.correct import as_written

    cmd, spk = build(as_written)

    cmd.say(OWNER, "deci que ya llegue")

    assert spk["parlante"].said == ["deci que ya llegue"]


def test_the_quiet_hours_do_not_pay_for_a_correction():
    """No se habla, así que no hay nada que corregir ni por qué esperar seis segundos."""
    from homeauto.quiet import QuietHours

    calls = []

    def correct(text):
        calls.append(text)
        return text

    speakers = {"parlante": FakeSpeaker("parlante")}
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        quiet=QuietHours.parse("23:00", "07:00"),
        correct=correct,
        clock=lambda: datetime(2026, 9, 4, 23, 30),
    )

    reply = commands.say(OWNER, "deci que ya llegue")

    assert calls == []
    assert "Decía: «deci que ya llegue»" in reply

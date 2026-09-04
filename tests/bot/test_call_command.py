"""Llamar a la casa a algo: la frase la arma la casa.

🔴 Es el otro lado de `/decir`. Ahí las palabras son de una persona y no se
tocan; acá la persona dio una intención —«llamar a todos a cenar»— y nunca
escribió qué decir, así que el texto es nuestro y se pule como el clima.
"""

from datetime import datetime

from homeauto.bot.commands import Commands
from homeauto.quiet import QuietHours

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
NIGHT = datetime(2026, 9, 4, 21, 30)


def build(polish=None, correct=None, quiet=None, clock=None, **speakers):
    speakers = speakers or {"parlante": FakeSpeaker("parlante"), "comedor": FakeSpeaker("comedor")}
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        quiet=quiet,
        polish=polish if polish is not None else (lambda text, must_keep=(): text),
        correct=correct if correct is not None else (lambda text: text),
        clock=clock or (lambda: NIGHT),
    )
    return commands, speakers


def test_it_says_a_sentence_the_person_never_wrote():
    """El caso que lo originó: «a cenar» a secas no es llamar a nadie."""
    cmd, spk = build()

    cmd.call(OWNER, "en todos a cenar")

    assert spk["parlante"].said == ["Vengan a cenar."]
    assert spk["comedor"].said == ["Vengan a cenar."]


def test_a_call_is_for_the_whole_house_by_default():
    """Llamar a uno solo a cenar no es lo que quiere decir «llamar»."""
    cmd, spk = build()

    cmd.call(OWNER, "a cenar")

    assert spk["parlante"].said == ["Vengan a cenar."]
    assert spk["comedor"].said == ["Vengan a cenar."]


def test_naming_a_room_still_wins():
    cmd, spk = build()

    cmd.call(OWNER, "en comedor a cenar")

    assert spk["comedor"].said == ["Vengan a cenar."]
    assert spk["parlante"].said == []


def test_the_meal_comes_from_the_clock():
    cmd, spk = build(clock=lambda: datetime(2026, 9, 4, 13, 0))

    cmd.call(OWNER, "a comer")

    assert spk["parlante"].said == ["Vengan a almorzar."]


def test_nothing_at_all_calls_to_the_meal_of_the_hour():
    cmd, spk = build()

    cmd.call(OWNER, "")

    assert spk["parlante"].said == ["Vengan a cenar."]


def test_the_sentence_is_polished_because_it_is_ours():
    cmd, spk = build(polish=lambda text, must_keep=(): "Chicos, a la mesa.")

    reply = cmd.call(OWNER, "a cenar")

    assert spk["parlante"].said == ["Chicos, a la mesa."]
    assert "«Chicos, a la mesa.»" in reply


def test_the_words_of_a_person_never_reach_the_polisher():
    """🔴 La regla que sigue en pie: `/decir` no se pule, se corrige."""
    seen = []

    def polish(text, must_keep=()):
        seen.append(text)
        return "REESCRITO"

    cmd, spk = build(polish=polish)

    cmd.say(OWNER, "en todos la comida está lista")

    assert seen == []
    assert spk["parlante"].said == ["la comida está lista"]
    assert spk["comedor"].said == ["la comida está lista"]


def test_the_quiet_hours_leave_it_written_and_cost_no_polishing():
    seen = []
    cmd, spk = build(
        polish=lambda text, must_keep=(): seen.append(text) or text,
        quiet=QuietHours.parse("23:00", "07:00"),
        clock=lambda: datetime(2026, 9, 4, 23, 30),
    )

    reply = cmd.call(OWNER, "a cenar")

    assert spk["parlante"].said == []
    assert seen == []
    assert "«Vengan a cenar.»" in reply


def test_an_unknown_room_is_said_and_nothing_is_spoken():
    cmd, spk = build()

    reply = cmd.call(OWNER, "en cocina,living a cenar")

    assert "No conozco" in reply
    assert spk["parlante"].said == []

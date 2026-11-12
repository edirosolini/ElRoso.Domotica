"""Lo que lee un chat cuando algo no está configurado: detalle para alertas, frase llana para la familia."""

import pytest

from homeauto.bot.commands import Commands
from homeauto.people import Person
from tests.conftest import FakeSpeaker, StubRegistry, make_config

ALERTS = 42
SECOND_ALERTS = 43
FAMILY = 7
DETAIL = "No tengo modelo para traducir. Cargá LLM_API_KEY en el archivo de entorno."


class FakeHousehold:
    """Un padrón con personas fijas, o que levanta al leerlo."""

    def __init__(self, *people, boom=None):
        self.people = people
        self.boom = boom

    def by_chat(self, chat_id):
        if self.boom:
            raise self.boom
        return next((person for person in self.people if person.chat_id == chat_id), None)


def build(household=None, alerts=(ALERTS,), **fields):
    return Commands(
        config=make_config(
            allowed={ALERTS, SECOND_ALERTS, FAMILY}, alert_chat_ids=frozenset(alerts), **fields
        ),
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        household=household,
    )


def test_an_alerts_chat_gets_the_technical_detail():
    cmd = build(FakeHousehold(Person(1, "Papá", ALERTS)))

    assert cmd._unconfigured(ALERTS, DETAIL) == DETAIL


def test_a_family_chat_is_told_who_to_ask():
    cmd = build(FakeHousehold(Person(1, "Papá", ALERTS)))

    assert cmd._unconfigured(FAMILY, DETAIL) == (
        "Esto todavía no está configurado. Avisale a Papá."
    )


def test_with_two_alerts_chats_it_names_both_in_a_stable_order():
    household = FakeHousehold(Person(1, "Papá", ALERTS), Person(2, "Mamá", SECOND_ALERTS))
    cmd = build(household, alerts=(SECOND_ALERTS, ALERTS))

    assert cmd._unconfigured(FAMILY, DETAIL) == (
        "Esto todavía no está configurado. Avisale a Papá o a Mamá."
    )


@pytest.mark.parametrize(
    "household",
    [None, FakeHousehold(), FakeHousehold(boom=RuntimeError("base rota"))],
    ids=["sin-padron", "sin-persona", "padron-que-falla"],
)
def test_without_a_name_it_points_to_whoever_runs_the_house(household):
    cmd = build(household)

    assert cmd._unconfigured(FAMILY, DETAIL) == (
        "Esto todavía no está configurado. Avisale a quien maneja la casa."
    )


def test_alert_names_says_who_runs_the_house():
    household = FakeHousehold(Person(1, "Papá", ALERTS), Person(2, "Mamá", SECOND_ALERTS))

    assert build(household, alerts=(SECOND_ALERTS, ALERTS)).alert_names() == "Papá o a Mamá"
    assert build(None).alert_names() == "quien maneja la casa"


PLAIN = "Esto todavía no está configurado. Avisale a Papá."
MENU_PARTS = {"meal_store": object(), "meal_planner": object()}
MEALS_OFF = {"menu_lunch_at": None, "menu_dinner_at": None}

UNCONFIGURED = [
    ("preguntar", lambda cmd, chat: cmd.ask(chat, "algo"), {}, {}, "LLM_API_KEY"),
    ("traducir", lambda cmd, chat: cmd.translate(chat, "hola"), {}, {}, "LLM_API_KEY"),
    ("menu-sin-modelo", lambda cmd, chat: cmd.menu(chat, ""), {}, {}, "LLM_API_KEY"),
    ("menu-apagado", lambda cmd, chat: cmd.menu(chat, ""), MENU_PARTS, MEALS_OFF, "MENU_LUNCH_AT"),
    ("agenda", lambda cmd, chat: cmd.agenda_command(chat, ""), {}, {}, "CALENDAR_URL_"),
    ("estado", lambda cmd, chat: cmd.status(chat, ""), {}, {}, "checks.json"),
    ("pantalla", lambda cmd, chat: cmd.screen(chat, ""), {}, {}, "API_TOKEN"),
]


def build_command(parts, fields):
    cmd = build(FakeHousehold(Person(1, "Papá", ALERTS)), **fields)
    for name, value in parts.items():
        setattr(cmd, name, value)
    return cmd


@pytest.mark.parametrize(
    "run, parts, fields, key", [case[1:] for case in UNCONFIGURED], ids=[c[0] for c in UNCONFIGURED]
)
def test_an_alerts_chat_still_reads_the_key_to_load(run, parts, fields, key):
    assert key in run(build_command(parts, fields), ALERTS)


@pytest.mark.parametrize(
    "run, parts, fields, key", [case[1:] for case in UNCONFIGURED], ids=[c[0] for c in UNCONFIGURED]
)
def test_a_family_chat_reads_it_plainly(run, parts, fields, key):
    assert run(build_command(parts, fields), FAMILY) == PLAIN

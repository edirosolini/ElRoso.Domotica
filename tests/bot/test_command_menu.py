"""El menú «/» de Telegram: un comando por tema, «ajustes» solo en los chats de alertas
y lo que no está en el menú, en `HELP`.
"""

import re

from homeauto.bot.commands import HELP, SETTINGS_TOPIC, TOPICS
from homeauto.main import ALL_COMMANDS, COMMAND_MENU, MENU_ALERTS

# Comandos fuera del menú, que siguen andando escritos y están en `HELP`.
OUT_OF_MENU = (
    "decir",
    "llamar",
    "alarma",
    "recordar",
    "lista",
    "compras",
    "equipos",
    "timer",
    "cancelar",
    "volumen",
    "parar",
    "apagar",
    "clima",
    "agenda",
    "estado",
    "usar",
    "calcular",
    "agregar",
    "pendientes",
    "sacar",
    "traducir",
    "posponer",
    "pastillas",
    "vacaciones",
    "turnos",
    "pantalla",
    "menu",
    "depurar",
)

VALID = re.compile(r"^[a-z0-9_]{1,32}$")


def names(menu):
    return [name for name, _ in menu]


def test_the_general_menu_is_one_command_per_topic():
    assert names(COMMAND_MENU) == [
        "inicio", "avisos", "parlante", "comida", "hoy", "preguntar", "silencio", "ayuda",
    ]


def test_every_topic_but_the_settings_is_in_the_general_menu():
    assert set(TOPICS) - {SETTINGS_TOPIC} <= set(names(COMMAND_MENU))


def test_the_alert_menu_is_the_general_one_plus_the_settings():
    assert names(MENU_ALERTS) == names(COMMAND_MENU) + [SETTINGS_TOPIC]
    assert MENU_ALERTS[: len(COMMAND_MENU)] == COMMAND_MENU


def test_the_settings_are_not_in_the_general_menu():
    assert SETTINGS_TOPIC not in names(COMMAND_MENU)


def test_every_menu_entry_is_a_registered_command():
    unknown = [name for name in names(MENU_ALERTS) if name not in ALL_COMMANDS]
    assert unknown == [], f"El menú ofrece comandos que no existen: {unknown}"


def test_menu_names_are_valid_for_telegram():
    invalid = [name for name in names(MENU_ALERTS) if not VALID.fullmatch(name)]
    assert invalid == []


def test_menu_has_no_duplicates():
    assert len(names(MENU_ALERTS)) == len(set(names(MENU_ALERTS)))


def test_every_entry_has_a_usable_description():
    for name, description in MENU_ALERTS:
        assert description.strip(), f"/{name} sin descripción"
        assert len(description) <= 256, f"/{name}: Telegram corta en 256 caracteres"


def test_the_descriptions_have_no_command_syntax():
    for name, description in MENU_ALERTS:
        assert "/" not in description, f"/{name}: la descripción nombra un comando"


def test_what_left_the_menu_is_still_offered_somewhere():
    menu = set(names(MENU_ALERTS))
    for name in OUT_OF_MENU:
        assert name not in menu, f"/{name} volvió al menú"
        assert name in ALL_COMMANDS, f"/{name} dejó de existir"
        assert f"/{name}" in HELP, f"/{name} no está en el menú ni en la ayuda"

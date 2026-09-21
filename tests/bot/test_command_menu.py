"""The '/' menu in Telegram only exists if the bot registers its commands.

Without setMyCommands everything works but is invisible: you have to know the
commands by heart. The menu is the short list; `HELP` is the whole catalogue.
"""

import re

from homeauto.bot.commands import HELP
from homeauto.main import ALL_COMMANDS, COMMAND_MENU

# Out of the menu on purpose: they still work typed and stay listed in HELP.
OUT_OF_MENU = (
    "timer",
    "cancelar",
    "volumen",
    "parar",
    "apagar",
    "clima",
    "agenda",
    "estado",
    "usar",
)

VALID = re.compile(r"^[a-z0-9_]{1,32}$")


def test_menu_is_not_empty():
    assert COMMAND_MENU


def test_every_menu_entry_is_a_registered_command():
    unknown = [name for name, _ in COMMAND_MENU if name not in ALL_COMMANDS]
    assert unknown == [], f"El menú ofrece comandos que no existen: {unknown}"


def test_menu_names_are_valid_for_telegram():
    invalid = [name for name, _ in COMMAND_MENU if not VALID.fullmatch(name)]
    assert invalid == []


def test_menu_has_no_duplicates():
    names = [name for name, _ in COMMAND_MENU]
    assert len(names) == len(set(names))


def test_every_entry_has_a_usable_description():
    for name, description in COMMAND_MENU:
        assert description.strip(), f"/{name} sin descripción"
        assert len(description) <= 256, f"/{name}: Telegram corta en 256 caracteres"


def test_the_commands_people_use_are_in_the_menu():
    names = {name for name, _ in COMMAND_MENU}
    for essential in ("decir", "alarma", "lista", "silencio", "ayuda"):
        assert essential in names, f"/{essential} no aparecería en el menú"


def test_the_menu_stays_short():
    assert len(COMMAND_MENU) <= 10, "el menú vuelve a ser una lista que nadie lee"


def test_what_left_the_menu_is_still_offered_somewhere():
    for name in OUT_OF_MENU:
        assert name in ALL_COMMANDS, f"/{name} dejó de existir"
        assert f"/{name}" in HELP, f"/{name} no está en el menú ni en la ayuda"

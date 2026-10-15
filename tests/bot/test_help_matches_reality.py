import re

from homeauto.bot.commands import HELP
from homeauto.main import ALL_COMMANDS

MENTIONED = re.compile(r"/([a-z_]+)")


def test_help_only_promises_commands_that_exist():
    promised = set(MENTIONED.findall(HELP))
    missing = promised - set(ALL_COMMANDS)

    assert missing == set(), f"La ayuda ofrece comandos que no están registrados: {missing}"


def test_help_mentions_the_commands_people_actually_need():
    for essential in ("decir", "timer", "alarma", "lista", "cancelar"):
        assert f"/{essential}" in HELP, f"/{essential} no figura en la ayuda"


def test_help_names_the_monthly_form_of_reminders_and_alarms():
    assert "/recordar mensual 10 9:00 pagar la luz" in HELP
    assert "/alarma mensual 10 9:00 pagar la luz" in HELP

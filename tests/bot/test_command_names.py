import re

from homeauto.main import ALL_COMMANDS

# Telegram rejects anything outside this shape at handler construction time,
# so an accented alias only blows up once the service is already deployed.
VALID = re.compile(r"^[a-z0-9_]{1,32}$")


def test_every_command_name_is_valid_for_telegram():
    invalid = [name for name in ALL_COMMANDS if not VALID.fullmatch(name)]
    assert invalid == [], f"Telegram va a rechazar estos comandos: {invalid}"


def test_there_are_no_duplicate_command_names():
    assert len(ALL_COMMANDS) == len(set(ALL_COMMANDS))

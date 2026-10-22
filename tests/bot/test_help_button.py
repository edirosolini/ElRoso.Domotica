"""«ayuda» como botón: la misma ayuda que /ayuda en Telegram, para la pantalla."""

import pytest

from homeauto.bot.commands import CHATLESS_ONLY, HELP, Commands

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42


def build():
    return Commands(config=make_config((OWNER,)), speakers=StubRegistry(parlante=FakeSpeaker()))


def test_the_help_button_answers_the_same_as_slash_ayuda():
    cmd = build()

    assert cmd.press(OWNER, "ayuda") == HELP == cmd.start(OWNER)


def test_a_person_without_telegram_cannot_ask_for_help():
    assert build().press_without_chat("ayuda") == CHATLESS_ONLY


@pytest.mark.parametrize("name", ["ayuda", "cancelar", "clima", "depurar"])
def test_a_command_and_help_can_be_typed_with_a_slash(name):
    assert build().typed(name)


@pytest.mark.parametrize("name", ["hecho", "borrar", "callar", "confirmar", "nada", "", "tiempo"])
def test_button_only_and_unknown_names_cannot_be_typed(name):
    assert not build().typed(name)

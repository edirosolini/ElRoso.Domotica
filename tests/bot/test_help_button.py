"""«ayuda» como botón y como comando: la corta con los temas, y la completa si se pide."""

import re

import pytest

from homeauto.bot.commands import CHATLESS_ONLY, HELP, HELP_SHORT, Commands, with_actions
from homeauto.main import ALL_COMMANDS

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42


def build():
    return Commands(config=make_config((OWNER,)), speakers=StubRegistry(parlante=FakeSpeaker()))


def test_the_help_button_answers_the_same_as_slash_ayuda():
    cmd = build()

    assert with_actions(cmd.press, OWNER, "ayuda") == with_actions(cmd.help, OWNER, "")


def test_the_short_help_comes_with_the_topics():
    reply = with_actions(build().help, OWNER, "")

    assert reply.text == HELP_SHORT
    assert any(data.startswith("tema ") for _, data in reply.actions)


@pytest.mark.parametrize("text", ["completa", " Completa "])
def test_the_whole_catalogue_is_asked_for(text):
    assert build().help(OWNER, text) == HELP


def test_the_help_button_can_ask_for_the_whole_catalogue():
    assert build().press(OWNER, "ayuda completa") == HELP


def test_the_short_help_is_short():
    assert len(HELP_SHORT.splitlines()) <= 12


@pytest.mark.parametrize("syntax", ["<", "lun-vie", "#"])
def test_the_short_help_has_no_syntax(syntax):
    assert syntax not in HELP_SHORT


def test_the_short_help_only_names_commands_that_exist():
    named = set(re.findall(r"/([a-z_]+)", HELP_SHORT))

    assert named <= set(ALL_COMMANDS)


def test_the_short_help_shows_examples_in_plain_words():
    assert "avisame mañana a las 9 que llame al médico" in HELP_SHORT
    assert "silencio una hora" in HELP_SHORT


def test_a_person_without_telegram_cannot_ask_for_help():
    assert build().press_without_chat("ayuda") == CHATLESS_ONLY


@pytest.mark.parametrize("name", ["ayuda", "cancelar", "clima", "depurar"])
def test_a_command_and_help_can_be_typed_with_a_slash(name):
    assert build().typed(name)


@pytest.mark.parametrize("name", ["hecho", "borrar", "callar", "confirmar", "nada", "", "tiempo"])
def test_button_only_and_unknown_names_cannot_be_typed(name):
    assert not build().typed(name)

"""El botón de «Posponer» abajo del aviso de una alarma."""

import asyncio
import threading

import pytest
from telegram import InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

from homeauto import main

ACTIONS = (("Posponer 10 min", "posponer 10m"),)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


@pytest.mark.asyncio
async def test_the_notifier_draws_the_actions_as_buttons():
    bot = FakeBot()
    notifier = main.ChatNotifier(bot)
    notifier.bind(asyncio.get_running_loop())

    await asyncio.to_thread(notifier, 42, "⏰ arriba", ACTIONS)

    markup = bot.sent[0]["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    button = markup.inline_keyboard[0][0]
    assert button.text == "Posponer 10 min"
    assert button.callback_data == "posponer 10m"


@pytest.mark.asyncio
async def test_without_actions_there_are_no_buttons():
    bot = FakeBot()
    notifier = main.ChatNotifier(bot)
    notifier.bind(asyncio.get_running_loop())

    await asyncio.to_thread(notifier, 42, "🔔 resumen")

    assert bot.sent[0].get("reply_markup") is None


def test_the_snooze_button_fits_in_telegram():
    """Telegram rechaza un callback_data de más de 64 bytes."""
    for _label, data in main.SNOOZE_ACTIONS:
        assert len(data.encode()) <= 64


# --- el toque ----------------------------------------------------------------


class Recorder:
    def __init__(self):
        self.buttons = []

    def add_handler(self, handler):
        if isinstance(handler, CallbackQueryHandler):
            self.buttons.append(handler.callback)


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


class FakeQuery:
    def __init__(self, data, message):
        self.data = data
        self.message = message
        self.answered = False
        self.markup_removed = False

    async def answer(self):
        self.answered = True

    async def edit_message_reply_markup(self, reply_markup=None):
        self.markup_removed = reply_markup is None


class FakeUpdate:
    def __init__(self, data, chat_id=42):
        self.message = None
        self.callback_query = FakeQuery(data, FakeMessage())
        self.effective_chat = type("Chat", (), {"id": chat_id})()


class PressSpy:
    def __init__(self, answer="Pospuesto"):
        self.presses = []
        self.threads = []
        self.answer = answer

    def press(self, chat_id, data):
        self.presses.append((chat_id, data))
        self.threads.append(threading.current_thread().name)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def __getattr__(self, _name):
        return lambda *args, **kwargs: "ok"


def register(commands):
    app = Recorder()
    main.register(app, commands)
    assert len(app.buttons) == 1, "tiene que haber un handler para los botones"
    return app.buttons[0]


@pytest.mark.asyncio
async def test_a_tap_runs_the_command_off_the_loop_and_answers():
    commands = PressSpy()
    tap = register(commands)
    update = FakeUpdate("posponer 10m")

    await tap(update, None)

    assert commands.presses == [(42, "posponer 10m")]
    assert commands.threads[0] != threading.current_thread().name
    assert update.callback_query.answered
    assert update.callback_query.message.replies == ["Pospuesto"]


@pytest.mark.asyncio
async def test_a_tap_takes_the_button_away():
    """Dos toques no pueden posponer dos veces."""
    tap = register(PressSpy())
    update = FakeUpdate("posponer 10m")

    await tap(update, None)

    assert update.callback_query.markup_removed


@pytest.mark.asyncio
async def test_a_tap_that_blows_up_still_answers():
    tap = register(PressSpy(answer=RuntimeError("se rompió")))
    update = FakeUpdate("posponer 10m")

    await tap(update, None)

    assert update.callback_query.message.replies[0].startswith("🔴")


@pytest.mark.asyncio
async def test_an_update_without_a_tap_is_ignored():
    commands = PressSpy()
    tap = register(commands)
    update = FakeUpdate("posponer 10m")
    update.callback_query = None

    await tap(update, None)

    assert commands.presses == []


@pytest.mark.asyncio
async def test_a_button_that_cannot_be_removed_still_gets_an_answer():
    commands = PressSpy()
    tap = register(commands)
    update = FakeUpdate("posponer 10m")

    async def refuse(reply_markup=None):
        raise RuntimeError("message is not modified")

    update.callback_query.edit_message_reply_markup = refuse

    await tap(update, None)

    assert update.callback_query.message.replies == ["Pospuesto"]


class FakeButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


@pytest.mark.asyncio
async def test_a_tap_only_takes_away_the_button_it_used():
    """Ver el estado no puede llevarse puesto el botón de silenciar."""
    tap = register(PressSpy())
    update = FakeUpdate("estado")
    update.callback_query.message.reply_markup = type(
        "Markup",
        (),
        {"inline_keyboard": [[FakeButton("Ver estado", "estado"), FakeButton("Silenciar 1 h", "silencio 1h")]]},
    )()
    kept = []

    async def keep(reply_markup=None):
        kept.append(reply_markup)

    update.callback_query.edit_message_reply_markup = keep

    await tap(update, None)

    rows = kept[0].inline_keyboard
    assert [[button.callback_data for button in row] for row in rows] == [["silencio 1h"]]

"""The command work must not run on the event loop.

Discovery uses zeroconf, which does blocking I/O: called from inside a running
asyncio loop it silently finds nothing, and every command answers "no encontré
el dispositivo". It also freezes the bot while Piper synthesizes.
"""

import asyncio
import threading

import pytest

from homeauto import main


class Recorder:
    """Stands in for Application, keeping the callbacks that get registered."""

    def __init__(self):
        self.callbacks = []

    def add_handler(self, handler):
        self.callbacks.append(handler.callback)


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, answer):
        self.replies.append(answer)


class FakeUpdate:
    def __init__(self, text, chat_id=42):
        self.message = FakeMessage(text)
        self.effective_chat = type("Chat", (), {"id": chat_id})()


class ThreadSpyCommands:
    """Every command records which thread it ran on."""

    def __init__(self):
        self.threads = []

    def _record(self, *_args):
        self.threads.append(threading.current_thread().name)
        return "ok"

    start = say = volume = stop = where = timer = alarm = list = cancel = _record
    devices = use = turn_off = _record


@pytest.mark.asyncio
async def test_no_command_runs_on_the_event_loop():
    app = Recorder()
    commands = ThreadSpyCommands()
    main.register(app, commands)

    loop_thread = threading.current_thread().name
    assert app.callbacks, "no se registró ningún handler"

    for callback in app.callbacks:
        update = FakeUpdate("/decir hola")
        await callback(update, None)
        assert update.message.replies == ["ok"]

    assert commands.threads, "ningún comando se ejecutó"
    on_loop = [name for name in commands.threads if name == loop_thread]
    assert on_loop == [], f"{len(on_loop)} comandos corrieron en el event loop"


@pytest.mark.asyncio
async def test_every_registered_command_replies():
    app = Recorder()
    main.register(app, ThreadSpyCommands())

    for callback in app.callbacks:
        update = FakeUpdate("/algo con argumentos")
        await callback(update, None)
        assert len(update.message.replies) == 1

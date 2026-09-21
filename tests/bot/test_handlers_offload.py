"""The command work must not run on the event loop.

Discovery uses zeroconf, which does blocking I/O: called from inside a running
asyncio loop it silently finds nothing, and every command answers "no encontré
el dispositivo". It also freezes the bot while Piper synthesizes.
"""

import asyncio
import threading

import pytest

from homeauto import main
from homeauto.bot.commands import Reply


class Recorder:
    """Stands in for Application, keeping the callbacks that get registered."""

    def __init__(self):
        self.callbacks = []

    def add_handler(self, handler):
        self.callbacks.append(handler.callback)


class FakeFile:
    async def download_as_bytearray(self):
        return bytearray(b"OggS\x00fake")


class FakeVoice:
    duration = 4
    mime_type = "audio/ogg"

    async def get_file(self):
        return FakeFile()


class FakeSent:
    """Lo que devuelve reply_text: se edita cuando llega la respuesta."""

    def __init__(self, text, message):
        self.text = text
        self.message = message

    async def edit_text(self, answer):
        self.message.edits.append(answer)


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.voice = FakeVoice()
        self.replies = []
        self.edits = []

    async def reply_text(self, answer):
        self.replies.append(answer)
        return FakeSent(answer, self)

    @property
    def answers(self):
        """Lo que el usuario termina leyendo."""
        return self.edits or self.replies


class FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id
        self.actions = []

    async def send_action(self, action):
        self.actions.append(action)


class FakeUpdate:
    def __init__(self, text, chat_id=42):
        self.message = FakeMessage(text)
        self.effective_chat = FakeChat(chat_id)


class ThreadSpyCommands:
    """Every command records which thread it ran on."""

    def __init__(self):
        self.threads = []

    def _record(self, *_args):
        self.threads.append(threading.current_thread().name)
        return "ok"

    start = say = call = volume = stop = where = timer = alarm = list = cancel = _record
    devices = use = turn_off = weather = agenda_command = _record
    status = silence = speak = ask = free_text = _record

    def heard(self, *_args, **_kwargs):
        # Lo real devuelve un Reply, no un string.
        return Reply(self._record())


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
        assert update.message.answers == ["ok"]

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
        assert len(update.message.answers) == 1


@pytest.mark.asyncio
async def test_it_says_it_is_working_before_doing_anything():
    """El indicador de Telegram no se ve en todos los clientes: va un mensaje."""
    app = Recorder()
    main.register(app, ThreadSpyCommands())

    for callback in app.callbacks:
        update = FakeUpdate("/preguntar algo que tarda")
        await callback(update, None)
        assert update.message.replies[0] == main.WORKING


@pytest.mark.asyncio
async def test_the_answer_replaces_the_waiting_message():
    """Una sola burbuja: la de «procesando» se convierte en la respuesta."""
    app = Recorder()
    main.register(app, ThreadSpyCommands())

    for callback in app.callbacks:
        update = FakeUpdate("/decir hola")
        await callback(update, None)
        assert update.message.replies == [main.WORKING], "no manda una burbuja de más"
        assert update.message.edits == ["ok"]


class ExplodingCommands:
    """Un comando que se rompe: el chat tiene que enterarse igual."""

    def _boom(self, *_args, **_kwargs):
        raise RuntimeError("Address already in use")

    start = say = call = volume = stop = where = timer = alarm = list = cancel = _boom
    devices = use = turn_off = weather = agenda_command = _boom
    status = silence = speak = ask = free_text = heard = _boom


@pytest.mark.asyncio
async def test_a_command_that_blows_up_still_answers():
    """Un error dejaba al mensaje sin respuesta y parecía colgado."""
    app = Recorder()
    main.register(app, ExplodingCommands())

    for callback in app.callbacks:
        update = FakeUpdate("/decir hola")
        await callback(update, None)
        assert update.message.answers, "el mensaje quedó sin contestar"
        answer = update.message.answers[0]
        assert answer.startswith("🔴"), "un error tiene que verse como un error"
        assert "no pude procesar" in answer.lower()
        assert "Address already in use" in answer, "qué se rompió, no solo que se rompió"

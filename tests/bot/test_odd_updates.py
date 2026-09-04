"""Updates que no son un mensaje nuevo.

🔴 Con `allowed_updates=ALL_TYPES` también llegan las ediciones, y ahí
`update.message` viene en None. El handler hacía `update.message.reply_text` de
una y reventaba con AttributeError, que en el log aparece como "No error
handlers are registered" y en Telegram como silencio.

Peor que el crash: antes de reventar, el comando ya se había ejecutado con el
argumento vacío, porque el texto se sacaba del mismo `update.message` que no
estaba. Editar "/decir hola" corría un `/decir` sin nada.
"""

import pytest

from homeauto import main


class Recorder:
    def __init__(self):
        self.callbacks = []

    def add_handler(self, handler):
        self.callbacks.append(handler.callback)


class SpyCommands:
    def __init__(self):
        self.calls = []

    def _record(self, chat_id, text=""):
        self.calls.append((chat_id, text))
        return "ok"

    start = say = call = volume = stop = where = timer = alarm = list = cancel = _record
    devices = use = turn_off = weather = agenda_command = _record
    status = silence = speak = ask = free_text = _record


class EditedUpdate:
    """Una edición: trae edited_message y `message` en None."""

    def __init__(self, text, chat_id=42):
        self.message = None
        self.effective_chat = type("Chat", (), {"id": chat_id})()
        self.edited_message = type("Msg", (), {"text": text})()


@pytest.mark.asyncio
async def test_an_edited_message_does_not_crash():
    app = Recorder()
    commands = SpyCommands()
    main.register(app, commands)

    for callback in app.callbacks:
        await callback(EditedUpdate("/decir hola"), None)  # no explota


@pytest.mark.asyncio
async def test_an_edited_message_does_not_run_the_command_again():
    """Corregir un typo no puede poner una segunda alarma."""
    app = Recorder()
    commands = SpyCommands()
    main.register(app, commands)

    for callback in app.callbacks:
        await callback(EditedUpdate("/alarma 7:30 arriba"), None)

    assert commands.calls == [], "una edición no vuelve a ejecutar el comando"

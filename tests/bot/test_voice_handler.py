"""El cableado de una nota de voz: bajarla y mandarla a los comandos."""

import threading

import pytest

from homeauto import main
from homeauto.bot.commands import Reply


class Recorder:
    def __init__(self):
        self.callbacks = []
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)
        self.callbacks.append(handler.callback)


class FakeFile:
    def __init__(self, data):
        self.data = data

    async def download_as_bytearray(self):
        return bytearray(self.data)


class FakeVoice:
    def __init__(self, data=b"OggS\x00fake", duration=4, mime_type="audio/ogg"):
        self.data = data
        self.duration = duration
        self.mime_type = mime_type
        self.downloads = 0

    async def get_file(self):
        self.downloads += 1
        return FakeFile(self.data)


class FakeSent:
    def __init__(self, text, message):
        self.text = text
        self.message = message

    async def edit_text(self, answer):
        self.message.edits.append(answer)

    async def delete(self):
        self.message.deleted.append(self.text)


class FakeMessage:
    def __init__(self, voice=None, text=""):
        self.text = text
        self.voice = voice
        self.replies = []
        self.edits = []
        self.deleted = []
        self.voices = []

    async def reply_text(self, answer):
        self.replies.append(answer)
        return FakeSent(answer, self)

    async def reply_voice(self, recorded):
        self.voices.append(recorded.read())


class FakeUpdate:
    def __init__(self, voice=None, text="", chat_id=42):
        self.message = FakeMessage(voice, text)
        self.effective_chat = type("Chat", (), {"id": chat_id})()


class SpyCommands:
    def __init__(self, audio_reply=None):
        self.heard_calls = []
        self.threads = []
        self.audio_reply = audio_reply

    def heard(self, chat_id, audio, mime="audio/ogg"):
        self.heard_calls.append((chat_id, bytes(audio), mime))
        self.threads.append(threading.current_thread().name)
        return Reply("🎤 «hola»\nEntendí: /clima", self.audio_reply)

    def _nothing(self, *_args):
        return "ok"

    def __getattr__(self, _name):
        return self._nothing


def voice_callback(app):
    """El único handler registrado para notas de voz."""
    from telegram.ext import filters

    found = [h.callback for h in app.handlers if getattr(h, "filters", None) is filters.VOICE]
    assert len(found) == 1, "tiene que haber exactamente un handler de voz"
    return found[0]


@pytest.mark.asyncio
async def test_a_voice_note_reaches_the_commands_with_its_bytes():
    app, commands = Recorder(), SpyCommands()
    main.register(app, commands)
    update = FakeUpdate(voice=FakeVoice(b"OggS\x00audio"))

    for callback in app.callbacks:
        await callback(update, None)

    assert (42, b"OggS\x00audio", "audio/ogg") in commands.heard_calls


@pytest.mark.asyncio
async def test_listening_does_not_run_on_the_event_loop():
    app, commands = Recorder(), SpyCommands()
    main.register(app, commands)
    update = FakeUpdate(voice=FakeVoice())

    for callback in app.callbacks:
        await callback(update, None)

    assert commands.threads
    assert threading.current_thread().name not in commands.threads


@pytest.mark.asyncio
async def test_a_long_audio_is_turned_away_before_downloading_it():
    app, commands = Recorder(), SpyCommands()
    main.register(app, commands)
    voice = FakeVoice(duration=main.MAX_VOICE_SECONDS + 1)
    update = FakeUpdate(voice=voice)

    for callback in app.callbacks:
        await callback(update, None)

    assert commands.heard_calls == []
    assert voice.downloads == 0
    assert "largo" in " ".join(update.message.replies).lower()


@pytest.mark.asyncio
async def test_a_message_without_voice_is_not_listened_to():
    app, commands = Recorder(), SpyCommands()
    main.register(app, commands)
    update = FakeUpdate(text="hola")

    for callback in app.callbacks:
        await callback(update, None)

    assert commands.heard_calls == []


@pytest.mark.asyncio
async def test_an_answer_with_audio_comes_back_as_a_voice_note(tmp_path):
    recorded = tmp_path / "respuesta.ogg"
    recorded.write_bytes(b"OggS-respuesta")
    app, commands = Recorder(), SpyCommands(audio_reply=recorded)
    main.register(app, commands)
    update = FakeUpdate(voice=FakeVoice())

    await voice_callback(app)(update, None)

    assert update.message.voices == [b"OggS-respuesta"]
    # Con el audio alcanza: la burbuja de espera se borra y no queda texto.
    assert update.message.edits == []
    assert update.message.deleted == [main.WORKING]


@pytest.mark.asyncio
async def test_without_audio_the_answer_comes_back_in_writing():
    """Si no se pudo grabar, el texto es lo único que queda."""
    app, commands = Recorder(), SpyCommands()
    main.register(app, commands)
    update = FakeUpdate(voice=FakeVoice())

    await voice_callback(app)(update, None)

    assert update.message.edits, "sin audio, el texto no puede faltar"
    assert update.message.deleted == []

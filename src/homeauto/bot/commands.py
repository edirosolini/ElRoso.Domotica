"""Command logic, free of any Telegram plumbing.

Every method takes the chat id and the raw argument text, and returns the reply
to send back. Device failures become sentences, never tracebacks: the person on
the other side is holding a phone, not a log viewer.
"""

from __future__ import annotations

import logging

from homeauto.config import Config
from homeauto.voice.caster import CastError
from homeauto.voice.tts import TtsError

log = logging.getLogger(__name__)

DEVICE_ERRORS = (CastError, TtsError)

HELP = """Hola. Le hablo al parlante de casa.

/decir <texto> — lo dice ahora
/volumen <0-100> — cambia el volumen
/parar — corta lo que esté sonando
/donde — qué dispositivo estoy usando"""


class Commands:
    def __init__(self, config: Config, speaker):
        self.config = config
        self.speaker = speaker

    def _denial(self, chat_id: int) -> str | None:
        """Returns the refusal to send, or None when the chat may proceed."""
        if self.config.is_allowed(chat_id):
            return None
        log.warning("chat %s rechazado", chat_id)
        return "No estás en la lista. Pedile al dueño que agregue tu ID: " + str(chat_id)

    def _enrollment_hint(self, chat_id: int) -> str:
        # While the whitelist is empty anyone can drive the speaker. Say so, and
        # hand over the id needed to close it.
        if not self.config.is_open_enrollment:
            return ""
        return (
            f"\n\n⚠️ El bot está abierto: cualquiera que lo encuentre puede usarlo."
            f"\nTu chat ID es {chat_id}. Ponelo en ALLOWED_CHAT_IDS y reiniciá el servicio."
        )

    def start(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial
        return HELP + self._enrollment_hint(chat_id)

    def say(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        text = text.strip()
        if not text:
            return "¿Qué querés que diga? Ej: /decir la cena está lista"

        try:
            self.speaker.say(text)
        except DEVICE_ERRORS as exc:
            log.exception("no se pudo decir '%s'", text)
            return f"No pude decirlo: {exc}"
        return f"Dicho: «{text}»" + self._enrollment_hint(chat_id)

    def volume(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            percent = int(text.strip())
        except ValueError:
            return "El volumen va como número de 0 a 100. Ej: /volumen 40"

        try:
            self.speaker.set_volume(percent)
        except DEVICE_ERRORS as exc:
            return f"No pude cambiar el volumen: {exc}"
        return f"Volumen en {percent}"

    def stop(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            self.speaker.stop()
        except DEVICE_ERRORS as exc:
            return f"No pude parar: {exc}"
        return "Cortado"

    def where(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            return f"Estoy hablando por: {self.speaker.device_name()}"
        except DEVICE_ERRORS as exc:
            return f"No encuentro el dispositivo: {exc}"

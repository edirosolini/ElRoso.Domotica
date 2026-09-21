"""Una nota de voz convertida en las palabras que dijo una persona."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

MIME = "audio/ogg"
# Subir el audio tarda más que pedir una reescritura: con los seis del
# pulidor, una nota de voz corta ya daba timeout.
TIMEOUT = 30
# Un comando dicho es una oración.
MAX_CHARS = 300
# What the model answers when there is nothing to transcribe.
NOTHING = "NADA"

PROMPT = (
    "Transcribí literal lo que dice este audio, en español rioplatense.\n"
    "Devolvé solo las palabras dichas: sin comillas, sin explicar, sin "
    "interpretar y sin agregar ni una palabra que no se haya dicho.\n"
    f"Si no se entiende nada, respondé exactamente {NOTHING}."
)

_QUOTES = "«»\"'“”"


class ListenError(Exception):
    """The audio could not be turned into words."""


class Transcriber:
    def __init__(self, model, prompt: str = PROMPT, max_chars: int = MAX_CHARS):
        self.model = model
        self.prompt = prompt
        self.max_chars = max_chars

    def __call__(self, audio: bytes, mime: str = MIME) -> str:
        try:
            heard = self.model(self.prompt, audio=audio, mime=mime)
        except Exception as exc:  # noqa: BLE001 - la falla se contesta en el chat
            raise ListenError(f"no pude escuchar el audio: {exc}") from exc

        heard = (heard or "").strip().strip(_QUOTES).strip()
        if not heard or heard.upper() == NOTHING:
            raise ListenError("no entendí lo que dice el audio")
        if len(heard) > self.max_chars:
            raise ListenError("el audio es muy largo para ser un pedido")
        return heard

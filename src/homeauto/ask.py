"""Contestar una pregunta en voz alta, sin que un dígito llegue al parlante.

La respuesta vuelve en dos mitades: `written` conserva todos los dígitos y va
al chat, `spoken` dice lo mismo con los números en palabras y es la única que
llega a Piper. Si la hablada no se puede confiar, la casa dice que dejó la
respuesta escrita.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

# Una respuesta con búsqueda sale a internet y vuelve, así que tiene mucho más
# que los seis segundos del pulidor.
ASK_TIMEOUT = 60

# Pasado esto la mitad hablada se descarta entera, no se recorta.
MAX_SPOKEN = 400
NOT_SPOKEN = "Te lo dejé escrito en el chat."

# Telegram rechaza un mensaje de más de 4096 caracteres.
MAX_WRITTEN = 3500

WRITTEN_TAG = "respuesta:"
SPOKEN_TAG = "voz:"

# La orden de buscar va primero y le dice que su información está vieja: al
# final, el modelo contesta de memoria.
PROMPT = """Buscá en Google antes de contestar. Hacelo siempre, aunque creas saber la
respuesta: tu información está vieja y la fecha de hoy no la sabés.

Con lo que encuentres, contestá en español rioplatense y devolvé exactamente dos
secciones, con estos rótulos:

RESPUESTA: la respuesta para leer en un chat. Breve y concreta, como mucho unas
pocas líneas. Acá sí podés usar números.
VOZ: la misma respuesta, para decirla en voz alta.
Si es corta, repetila entera y tal cual: un chiste, una definición o un dato se
arruinan si los resumís. Nunca la cuentes en tercera persona ni con "le respondió
que": si hay diálogo, dejá el diálogo.
Solo si la respuesta es larga —una lista, una enumeración— quedate con lo
principal en dos o tres oraciones.
Escribí todos los números con palabras y no uses ni un solo dígito.

Nada de saludos, emojis, ni comentarios tuyos.

Pregunta: {question}"""


class AskError(Exception):
    """No se pudo contestar la pregunta."""


@dataclass(frozen=True)
class Answer:
    """Lo que se lee y lo que se dice. No son el mismo texto."""

    spoken: str
    written: str


def _clean(text: str) -> str:
    """Saca el markdown que un modelo le pone a los rótulos que se le pidieron."""
    return re.sub(r"[*#`]", "", text)


class Asker:
    def __init__(
        self,
        model: Callable[[str], str],
        prompt: str = PROMPT,
        max_spoken: int = MAX_SPOKEN,
        max_written: int = MAX_WRITTEN,
        fallback: str = NOT_SPOKEN,
    ):
        self.model = model
        self.prompt = prompt
        self.max_spoken = max_spoken
        self.max_written = max_written
        self.fallback = fallback

    def ask(self, question: str) -> Answer:
        question = question.strip()
        if not question:
            raise AskError("¿Qué querés que pregunte?")

        try:
            # La pregunta viaja literal: reescribirla contestaría otra pregunta.
            reply = self.model(self.prompt.format(question=question))
        except Exception as exc:  # noqa: BLE001 - el usuario tiene un teléfono, no un log
            log.warning("no pude contestar la pregunta: %s", exc)
            raise AskError("No pude averiguarlo ahora. Probá de nuevo en un rato.") from exc

        written, spoken = self._split(_clean(reply or ""))
        if not written:
            raise AskError("El modelo no contestó nada.")

        return Answer(spoken=self._safe_to_say(spoken), written=written[: self.max_written])

    def _split(self, reply: str) -> tuple[str, str]:
        """La mitad escrita y la hablada, como las rotuló el modelo."""
        lowered = reply.lower()
        cut = lowered.find(SPOKEN_TAG)
        start = lowered.find(WRITTEN_TAG)

        if cut == -1:
            # Sin mitad hablada: todo es para leer.
            body = reply[start + len(WRITTEN_TAG):] if start != -1 else reply
            return body.strip(), ""

        spoken = reply[cut + len(SPOKEN_TAG):].strip()
        if start == -1 or start > cut:
            # Volvió solo la mitad hablada. Igual es una respuesta: se escribe.
            return spoken, spoken
        return reply[start + len(WRITTEN_TAG):cut].strip(), spoken

    def _safe_to_say(self, spoken: str) -> str:
        """La mitad hablada, o el puntero al chat cuando no se puede decir."""
        if not spoken:
            return self.fallback
        if any(character.isdigit() for character in spoken):
            # Piper lee un dígito como cardinal masculino suelto.
            log.info("la voz de la respuesta trae dígitos, la dejo escrita")
            return self.fallback
        if len(spoken) > self.max_spoken:
            log.info("la voz de la respuesta se fue de largo, la dejo escrita")
            return self.fallback
        return spoken

"""Answering a question out loud, without letting a digit reach the speaker.

A question is the one thing the house says that it did not generate itself: the
answer comes from a model with search, and search answers are made of years,
scores and counts. That is exactly what the synthesizer reads wrong.

🔴 So the answer comes back in two halves, the same split `watch.seq.Summary`
already makes: `written` keeps every digit and goes to the chat, `spoken` says
the same thing with the numbers in words and is the only half that reaches Piper.

⚠️ Spoken is not a *summary*. Asked to summarize, the model turned a joke into
reported speech —"el papá le responde que no sabe"— and the joke died. It only
condenses what is genuinely long, like a top ten.
When the spoken half cannot be trusted, the house says it left the answer
written — never the digits, and never nothing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

# A top ten said out loud is a minute of speaker. The chat can hold it, the
# house cannot: past this the spoken half is dropped, not truncated, because
# half a sentence is worse than a pointer to the chat.
# A grounded answer goes out to search and back. Measured against the real
# endpoint, a flash model answering four questions took between 8 and 40
# seconds, so thirty would have cut off the slowest ones. The six seconds the
# polisher waits are for a rewrite nobody is waiting on; here somebody asked
# and is watching the chat.
ASK_TIMEOUT = 60

# Measured: the answer to "top diez de los mejores goles de Messi" came back
# between 290 and 355 characters, so a tighter cap would drop a legitimate
# answer into the chat instead of saying it.
MAX_SPOKEN = 400
NOT_SPOKEN = "Te lo dejé escrito en el chat."

# Telegram refuses a message past 4096 characters.
MAX_WRITTEN = 3500

WRITTEN_TAG = "respuesta:"
SPOKEN_TAG = "voz:"

# 🔴 The order matters and so does the insistence. With "buscá si hace falta"
# at the end, the model searched in none of four questions and made up the
# current temperature. Told first, and told its knowledge is stale, it searches.
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
    """The question could not be answered."""


@dataclass(frozen=True)
class Answer:
    """What gets read, and what gets said. They are not the same text."""

    spoken: str
    written: str


def _clean(text: str) -> str:
    """Drops the markdown a model sprinkles on the labels it was asked for."""
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
            # ⚠️ The question travels verbatim. The words are somebody's, like
            # the text of /decir: rewriting them would answer another question.
            reply = self.model(self.prompt.format(question=question))
        except Exception as exc:  # noqa: BLE001 - el usuario tiene un teléfono, no un log
            log.warning("no pude contestar la pregunta: %s", exc)
            raise AskError("No pude averiguarlo ahora. Probá de nuevo en un rato.") from exc

        written, spoken = self._split(_clean(reply or ""))
        if not written:
            raise AskError("El modelo no contestó nada.")

        return Answer(spoken=self._safe_to_say(spoken), written=written[: self.max_written])

    def _split(self, reply: str) -> tuple[str, str]:
        """The written half and the spoken one, as the model labelled them."""
        lowered = reply.lower()
        cut = lowered.find(SPOKEN_TAG)
        start = lowered.find(WRITTEN_TAG)

        if cut == -1:
            # No spoken half: everything is for reading.
            body = reply[start + len(WRITTEN_TAG):] if start != -1 else reply
            return body.strip(), ""

        spoken = reply[cut + len(SPOKEN_TAG):].strip()
        if start == -1 or start > cut:
            # Only the spoken half came back. It is still an answer: write it.
            return spoken, spoken
        return reply[start + len(WRITTEN_TAG):cut].strip(), spoken

    def _safe_to_say(self, spoken: str) -> str:
        """The spoken half, or the pointer to the chat when it cannot be said."""
        if not spoken:
            return self.fallback
        if any(character.isdigit() for character in spoken):
            # 🔴 "a las 21" is said "a las veintiuno" and "672 goles",
            # "seiscientos setenta y dos goles" only if it is written that way.
            log.info("la voz de la respuesta trae dígitos, la dejo escrita")
            return self.fallback
        if len(spoken) > self.max_spoken:
            log.info("la voz de la respuesta se fue de largo, la dejo escrita")
            return self.fallback
        return spoken

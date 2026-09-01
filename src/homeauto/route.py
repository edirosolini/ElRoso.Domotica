"""Understanding a message that came without a slash.

The router decides *what* the person asked for; it never does it. `Commands`
already knows how to run every one of these, and the existing parsers already
know how to reject a bad argument, so this only has to name the command and
hand over its text.

🔴 The one thing it is not allowed to touch is what the house will say with its
own voice. `/decir` carries somebody's words, and a model asked to extract them
will happily improve them on the way out. So the payload of `decir` is checked
against the original message: what is not in there was invented, and an invented
message is worse than not understanding at all.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

COMMAND_TAG = "comando:"
ARGUMENT_TAG = "argumento:"
NONE_WORDS = {"ninguno", "ninguna", "nada", "none", ""}

# Only these can be reached without a slash. The model can answer anything, and
# anything outside this list is treated as a question instead of guessed at.
ROUTABLE = (
    "decir", "timer", "alarma", "lista", "cancelar", "silencio", "hablar",
    "volumen", "parar", "apagar", "clima", "agenda", "estado", "equipos",
    "usar", "preguntar",
)

# What the person says goes literally into these, so it cannot be reworded.
LITERAL_PAYLOAD = ("decir",)

# A leading «en comedor» / «en comedor,recamara» is targeting, not message: the
# router builds it, so it is allowed to appear in the argument without being in
# the original text.
_TARGET_PREFIX = re.compile(r"^en\s+[a-z0-9_-]+(?:\s*,\s*[a-z0-9_-]+)*\s+", re.IGNORECASE)

PROMPT = """Sos el intérprete de un bot de domótica de una casa. Leé el mensaje y decidí
qué comando quiso usar la persona.

Comandos y qué lleva cada uno:
- decir: el texto a decir en voz alta, tal cual lo escribió la persona
- timer: una duración y el mensaje, así: "10m sacá la pizza"
- alarma: una hora y el mensaje, así: "7:30 arriba"; para repetir, "diaria 7:30 arriba"
  o los días adelante, "lun-vie 5:30 arriba"
- lista: sin argumento, lo que está programado
- cancelar: el número a cancelar
- silencio: cuánto rato callarse, así: "2h"
- hablar: sin argumento, cancela el silencio
- volumen: un número de 0 a 100
- parar: sin argumento, corta lo que suena
- apagar: sin argumento, deja el equipo en reposo
- clima: sin argumento, el pronóstico
- agenda: sin argumento, o "mañana"
- estado: sin argumento, cómo están los servicios vigilados
- equipos: sin argumento, qué equipos hay
- usar: el equipo que pasa a ser el de siempre
- preguntar: una pregunta de conocimiento o de actualidad, para buscar la respuesta

Reglas:
- Si el mensaje es una pregunta, o no encaja claramente en ningún comando, contestá
  "COMANDO: ninguno".
- Si la persona nombra un equipo (parlante, comedor, recamara, tv), poné el argumento
  empezando con "en <equipo> ".
- 🔴 En "decir", el texto tiene que ser EXACTAMENTE las palabras del mensaje, pero
  SIN el verbo con que te lo pidieron y SIN el equipo. Eso va aparte. No lo
  reescribas, no lo completes, no lo corrijas.
- Las duraciones y horas convertilas al formato de arriba: "diez minutos" es "10m",
  "las siete y media" es "7:30".

Ejemplos:

Mensaje: decí que ya llegué
COMANDO: decir
ARGUMENTO: que ya llegué

Mensaje: decile a todos que la comida está lista
COMANDO: decir
ARGUMENTO: en todos la comida está lista

Mensaje: avisá en el comedor que salgo en cinco minutos
COMANDO: decir
ARGUMENTO: en comedor que salgo en cinco minutos

Mensaje: poneme un timer de diez minutos para sacar la pizza
COMANDO: timer
ARGUMENTO: 10m sacar la pizza

Mensaje: cuántos goles hizo Messi
COMANDO: preguntar
ARGUMENTO: cuántos goles hizo Messi

Contestá solo con dos líneas:
COMANDO: <nombre o ninguno>
ARGUMENTO: <el texto, o vacío>

Mensaje: {message}"""


class RouteError(Exception):
    """The message could not be interpreted at all."""


@dataclass(frozen=True)
class Decision:
    """The command the message meant, or nothing when it is a question."""

    command: str | None
    argument: str = ""

    @property
    def is_question(self) -> bool:
        return self.command is None


def _clean(text: str) -> str:
    return re.sub(r"[*#`]", "", text)


def _normalize(text: str) -> str:
    """Lowercased with runs of whitespace collapsed, for comparing wordings."""
    return " ".join(text.lower().split())


class Router:
    def __init__(
        self,
        model: Callable[[str], str],
        prompt: str = PROMPT,
        routable: tuple[str, ...] = ROUTABLE,
    ):
        self.model = model
        self.prompt = prompt
        self.routable = routable

    def route(self, message: str) -> Decision:
        message = message.strip()
        if not message:
            raise RouteError("Vino un mensaje vacío.")

        try:
            reply = self.model(self.prompt.format(message=message))
        except Exception as exc:  # noqa: BLE001
            # Never a silent question: sending "apagá la tele" out to a web
            # search is a worse answer than saying it was not understood.
            log.warning("no pude interpretar el mensaje: %s", exc)
            raise RouteError("No te entendí. Probá con /ayuda.") from exc

        command, argument = self._parse(_clean(reply or ""))
        if command not in self.routable:
            return Decision(None)

        if command in LITERAL_PAYLOAD and not self._faithful(argument, message):
            log.info("descarto el ruteo a %s: el texto no sale del mensaje", command)
            return Decision(None)

        return Decision(command, argument)

    def _parse(self, reply: str) -> tuple[str | None, str]:
        lowered = reply.lower()
        start = lowered.find(COMMAND_TAG)
        if start == -1:
            return None, ""

        cut = lowered.find(ARGUMENT_TAG, start)
        if cut == -1:
            command = reply[start + len(COMMAND_TAG):].strip()
            argument = ""
        else:
            command = reply[start + len(COMMAND_TAG):cut].strip()
            argument = reply[cut + len(ARGUMENT_TAG):].strip()

        command = command.lower().split()[0] if command.split() else ""
        if command in NONE_WORDS:
            return None, ""
        return command, argument

    def _faithful(self, argument: str, message: str) -> bool:
        """Whether what the house would say really came out of the message.

        The «en <equipo>» head is dropped first: that part is targeting the
        router adds, not words anybody typed.
        """
        payload = _TARGET_PREFIX.sub("", argument.strip())
        if not payload:
            return False
        return _normalize(payload) in _normalize(message)

"""Corregir cómo escribió una persona, sin cambiar lo que dijo.

Ortografía, acentos, puntuación y números en palabras. Todo lo que devuelve el
modelo se compara palabra por palabra con lo tipeado, y cualquier invento manda
el original al parlante. Tres licencias, y solo tres:

- Un dígito puede crecer hasta las palabras que lo dicen.
- Una palabra a una letra de la que volvió es la misma palabra, salvo las
  palabras cortas de `RISKY`.
- Una comida puede volverse otra comida, siguiendo el reloj.

Cualquier otra cosa es una reescritura, y reescribir las palabras de alguien no
es corregirlas.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime
from typing import Callable, Iterator

log = logging.getLogger(__name__)

# Cuántas palabras puede volverse un dígito: "veintiuno" es una, "nueve de la
# noche" son cuatro.
MAX_NUMBER_WORDS = 6
# Lugar para puntuación y números en palabras, no para una segunda oración.
MAX_GROWTH = 2.2

# Qué significa cada abreviatura de chat. Sin acentos: la comparación los saca
# igual.
ABBREVIATIONS = {
    "q": ["que"],
    "k": ["que"],
    "xq": ["porque"],
    "pq": ["porque"],
    "x": ["por"],
    "d": ["de"],
    "tb": ["tambien"],
    "tmb": ["tambien"],
    "xa": ["para"],
    "pa": ["para"],
    "bn": ["bien"],
    "dsp": ["despues"],
    "xfa": ["por", "favor"],
    "porfa": ["por", "favor"],
    "hs": ["horas"],
    "min": ["minutos"],
}

# El único vocabulario donde una palabra puede volverse otra distinta.
MEAL_WORDS = frozenset(
    {
        "comer", "comida", "almorzar", "almuerzo", "cenar", "cena",
        "desayunar", "desayuno", "merendar", "merienda",
    }
)

# Nunca se corrigen por parecido: cada una está a una letra de otra que
# significa lo contrario.
RISKY = frozenset(
    {
        "no", "ni", "si", "sin", "con", "mas", "menos", "me", "te", "le", "se",
        "mi", "tu", "su", "el", "la", "lo", "y", "o", "un", "una", "yo",
    }
)

# Cuándo cae cada comida, como rangos de hora, con cómo se llama y qué es
# hacerla. La última cruza la medianoche.
MEALS = (
    (5, 11, "el desayuno", "desayunar"),
    (11, 15, "el almuerzo", "almorzar"),
    (15, 19, "la merienda", "merendar"),
)
NIGHT_MEAL = ("la cena", "cenar")

PROMPT = """Corregí cómo está escrito este mensaje. Lo va a leer en voz alta un parlante
de una casa, en español rioplatense, y lo escribió una persona apurada.

Ahora son las {clock}, o sea la hora de {meal}.

Reglas:
- No cambies las palabras ni el orden: corregí ortografía, tildes, mayúsculas y puntuación.
- Escribí los números en palabras: "1 minuto" es "un minuto", "a las 21" es "a las nueve
  de la noche". No uses dígitos.
- Si el mensaje habla de comer sin decir qué comida es, usá la que corresponde a esta hora.
- No agregues saludos, aclaraciones ni comentarios tuyos.
- Respondé únicamente con el mensaje corregido.

Mensaje: {text}"""


def as_written(text: str) -> str:
    """Lo de siempre: decir exactamente lo que la persona tipeó."""
    return text


def meal_at(moment: datetime) -> str:
    """De qué comida es hora, en palabras."""
    return _meal(moment)[0]


def meal_verb(moment: datetime) -> str:
    """Qué es hacer esa comida: cenar, almorzar, desayunar, merendar."""
    return _meal(moment)[1]


def _meal(moment: datetime) -> tuple[str, str]:
    for start, end, name, verb in MEALS:
        if start <= moment.hour < end:
            return name, verb
    return NIGHT_MEAL


def _plain(word: str) -> str:
    """En minúsculas y sin acentos, que es lo que comparar palabras significa acá."""
    stripped = unicodedata.normalize("NFD", word.lower())
    return "".join(char for char in stripped if not unicodedata.combining(char))


def _words(text: str) -> list[str]:
    return [_plain(token) for token in re.findall(r"\d+|[^\W\d_]+", text, re.UNICODE)]


def _one_edit_apart(typed: str, fixed: str) -> bool:
    """Si una es la otra con una letra agregada, sacada o cambiada."""
    if abs(len(typed) - len(fixed)) > 1:
        return False
    if len(typed) < len(fixed):
        typed, fixed = fixed, typed

    edits = 0
    i = j = 0
    while i < len(typed) and j < len(fixed):
        if typed[i] == fixed[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        i += 1
        if len(typed) == len(fixed):
            j += 1
    return edits + (len(typed) - i) + (len(fixed) - j) <= 1


def _same_word(typed: str, fixed: str) -> bool:
    if typed == fixed:
        return True
    if typed in RISKY or fixed in RISKY or len(typed) < 3:
        return False
    return _one_edit_apart(typed, fixed)


class CorrectError(Exception):
    """No se pudo llegar al modelo, o contestó algo inservible."""


class Corrector:
    """Las palabras de alguien, escritas como el parlante tiene que leerlas."""

    def __init__(
        self,
        model: Callable[[str], str],
        prompt: str = PROMPT,
        clock: Callable[[], datetime] = datetime.now,
        max_growth: float = MAX_GROWTH,
    ):
        self.model = model
        self.prompt = prompt
        self.clock = clock
        self.max_growth = max_growth
        # Mismo texto, misma salida: `VoiceSynth` cachea por frase, y una
        # escritura distinta cada vez significaría sintetizar siempre.
        self._cache: dict[str, str] = {}

    def correct(self, text: str) -> str:
        if not text.strip():
            return text

        now = self.clock()
        # La comida va en la clave: la misma frase al mediodía y a la noche es
        # otra corrección, y el cache no puede servir la anterior.
        key = f"{meal_at(now)}\x00{text}"
        if key not in self._cache:
            self._cache[key] = self._ask(text, now)
        return self._cache[key]

    def _ask(self, text: str, now: datetime) -> str:
        prompt = self.prompt.format(
            text=text, clock=now.strftime("%H:%M"), meal=meal_at(now)
        )
        try:
            answer = self.model(prompt)
        except Exception as exc:  # noqa: BLE001 - nunca puede tumbar un aviso
            log.warning("no pude corregir el texto, va como lo escribieron: %s", exc)
            return text

        answer = (answer or "").strip()
        problem = self._problem_with(text, answer)
        if problem:
            log.info("descarto la corrección (%s), va el texto original", problem)
            return text
        return answer

    def _problem_with(self, text: str, answer: str) -> str:
        """Por qué no se puede confiar en la corrección, o "" si se puede."""
        if not answer:
            return "vino vacía"
        if any(character.isdigit() for character in answer):
            return "trae dígitos"
        if len(answer) > len(text) * self.max_growth:
            return "se fue de largo"
        if not self._same_words(_words(text), _words(answer)):
            return "cambió las palabras"
        return ""

    def _same_words(self, typed: list[str], fixed: list[str]) -> bool:
        """Si la respuesta son las mismas palabras, con solo las tres licencias.

        Se recorre como conjunto de posiciones alcanzables, porque un dígito
        puede valer por cualquier cantidad de palabras.
        """
        reachable = {0}
        for word in typed:
            landing: set[int] = set()
            for start in reachable:
                landing.update(self._lengths(word, fixed, start))
            reachable = landing
            if not reachable:
                return False
        return len(fixed) in reachable

    @staticmethod
    def _lengths(word: str, fixed: list[str], start: int) -> Iterator[int]:
        """Dónde puede terminar esta palabra tipeada, según las palabras de la respuesta."""
        if word.isdigit():
            # Un número en palabras: lo que haga falta para decirlo, sin dígitos.
            for size in range(1, MAX_NUMBER_WORDS + 1):
                chunk = fixed[start:start + size]
                if len(chunk) == size and not any(part.isdigit() for part in chunk):
                    yield start + size
            return

        if start >= len(fixed):
            return

        here = fixed[start]
        if _same_word(word, here):
            yield start + 1
        elif word in MEAL_WORDS and here in MEAL_WORDS:
            yield start + 1

        expansion = ABBREVIATIONS.get(word)
        if expansion and fixed[start:start + len(expansion)] == expansion:
            yield start + len(expansion)


def build(model: Callable[[str], str], clock: Callable[[], datetime] = datetime.now):
    """El callable que espera el resto del código, nunca el objeto."""
    return Corrector(model, clock=clock).correct

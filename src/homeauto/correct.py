"""Fixing how a person wrote something, without changing what they said.

🔴 This is not the polisher. The polisher rewords what *we* generated; here the
words are somebody's, so they come back in the same order and mostly the same:
spelling, accents, punctuation and numbers written out. Everything the model
gives back is checked word by word against what was typed, and anything it
invented sends the original to the speaker instead.

Three licences, and only three:

- **Numbers become words.** This is the reason the module exists: Piper reads a
  digit as a loose masculine cardinal, so "llego en 1 minuto" came out as
  "llego en uno minuto". A digit may grow into the words that say it.
- **A typo is a typo.** A word one letter away from what came back is taken as
  the same word. ⚠️ Short function words are left alone — "no" and "yo" are also
  one letter apart, and there the correction would flip the meaning.
- 🔴 **A meal follows the clock.** "es hora de comer" at half past nine at night
  is "es hora de cenar". It is the one place where a word may be swapped for a
  different word, it is limited to `MEAL_WORDS`, and it is why this thing knows
  what time it is. The owner asked for it by example.

Anything else — a word that appears, one that goes missing, a sentence turned
around — is a rewrite, and a rewrite of somebody's words is not a correction.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime
from typing import Callable, Iterator

log = logging.getLogger(__name__)

# How many words one digit is allowed to become: "veintiuno" is one, "nueve de
# la noche" is four. Past this it stopped saying a number and started talking.
MAX_NUMBER_WORDS = 6
# Room for punctuation and written-out numbers, not for a second sentence.
MAX_GROWTH = 2.2

# What a chat abbreviation stands for. Written without accents: the comparison
# strips them anyway.
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

# 🔴 The only vocabulary where one word may become a different one. They all
# mean the same thing said at another hour, so swapping them changes when, not
# what — and the hour is a fact the house already knows.
MEAL_WORDS = frozenset(
    {
        "comer", "comida", "almorzar", "almuerzo", "cenar", "cena",
        "desayunar", "desayuno", "merendar", "merienda",
    }
)

# ⚠️ Never corrected by proximity: every one of these is one letter away from
# another that means the opposite.
RISKY = frozenset(
    {
        "no", "ni", "si", "sin", "con", "mas", "menos", "me", "te", "le", "se",
        "mi", "tu", "su", "el", "la", "lo", "y", "o", "un", "una", "yo",
    }
)

# When each meal happens, as hour ranges, with what to call it and what it is
# to do it. The last one wraps past midnight.
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
    """The default: say exactly what the person typed."""
    return text


def meal_at(moment: datetime) -> str:
    """Which meal it is time for, in words."""
    return _meal(moment)[0]


def meal_verb(moment: datetime) -> str:
    """What it is to have that meal: cenar, almorzar, desayunar, merendar."""
    return _meal(moment)[1]


def _meal(moment: datetime) -> tuple[str, str]:
    for start, end, name, verb in MEALS:
        if start <= moment.hour < end:
            return name, verb
    return NIGHT_MEAL


def _plain(word: str) -> str:
    """Lowercase and without accents, which is what comparing words means here."""
    stripped = unicodedata.normalize("NFD", word.lower())
    return "".join(char for char in stripped if not unicodedata.combining(char))


def _words(text: str) -> list[str]:
    return [_plain(token) for token in re.findall(r"\d+|[^\W\d_]+", text, re.UNICODE)]


def _one_edit_apart(typed: str, fixed: str) -> bool:
    """Whether one is the other with a letter added, dropped or changed."""
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
    """The model could not be reached or answered something unusable."""


class Corrector:
    """Somebody's words, spelled the way the speaker should read them."""

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
        # Same text in, same text out: `VoiceSynth` caches by phrase, and a
        # different spelling every time would mean synthesizing every time.
        self._cache: dict[str, str] = {}

    def correct(self, text: str) -> str:
        if not text.strip():
            return text

        now = self.clock()
        # The meal is part of the key: the same sentence at noon and at night
        # is a different correction, and the cache must not hand over the other.
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
        """Why the correction cannot be trusted, or "" when it can."""
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
        """Whether the answer is the same words, allowing only the three licences.

        Walked as a set of reachable positions instead of one by one: a digit
        may stand for any number of words, so where the next word begins is not
        known until the one after it matches.
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
        """Where this typed word could end, given the answer's words."""
        if word.isdigit():
            # A number in words: whatever it takes to say it, and no digits.
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
    """The callable the rest of the code expects, never the object.

    🔴 A `Corrector` is not callable on its own, and the wiring already shipped
    that bug once with the polisher: the service started fine and blew up with
    a TypeError the first time somebody spoke.
    """
    return Corrector(model, clock=clock).correct

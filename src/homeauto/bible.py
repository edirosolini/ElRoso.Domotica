"""El versículo del día de YouVersion, en la Nueva Traducción Viviente.

La lista del año dice qué referencia toca hoy; el texto se pide aparte, en la
NTV. El versículo va literal: solo la referencia se pone en palabras. Uno que
trae un dígito no se dice, queda escrito.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Callable
from urllib.parse import urlencode

from homeauto.verbalize import cardinal

log = logging.getLogger(__name__)

# Endpoints internos de bible.com: la página pública exige JavaScript.
VOTD_URL = "https://nodejs.bible.com/api/moments/votd/3.1"
VERSE_URL = "https://nodejs.bible.com/api/bible/verse/3.1"
NTV = 127
TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; domotica/1.0)"

_ORDINALS = {"1": ("Primero", "Primera"), "2": ("Segundo", "Segunda"), "3": ("Tercero", "Tercera")}
# Las cartas numeradas se nombran en femenino: "Primera de Juan".
_LETTERS = frozenset({"Corintios", "Tesalonicenses", "Timoteo", "Pedro", "Juan"})
_SHOUTED = re.compile(r"\b[A-ZÁÉÍÓÚÑÜ]{2,}\b")
_REFERENCE = re.compile(r"^(?P<book>.+?)\s+(?P<chapter>\d+):(?P<verse>\d+)$")


@dataclass(frozen=True)
class Passage:
    """Lo que dice la casa y lo que queda en el chat."""

    spoken: str
    written: str


def fetch_json(url: str) -> dict:
    """La llamada real. Se importa tarde para que los tests no toquen la red."""
    import requests

    response = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.json()


def _spoken_book(book: str) -> str:
    """ "1 Juan" -> "Primera de Juan", "2 Reyes" -> "Segundo de Reyes"."""
    number, _, name = book.partition(" ")
    if number not in _ORDINALS or not name:
        return book
    masculine, feminine = _ORDINALS[number]
    return f"{feminine if name in _LETTERS else masculine} de {name}"


class VerseOfTheDay:
    def __init__(
        self,
        fetch: Callable[[str], dict] = fetch_json,
        today: Callable[[], date] = date.today,
    ):
        self.fetch = fetch
        self.today = today

    def references(self) -> list[str]:
        """Las referencias USFM de hoy: una, o varias seguidas."""
        day = self.today().timetuple().tm_yday
        query = urlencode({"language_tag": "es"})
        for entry in self.fetch(f"{VOTD_URL}?{query}").get("votd", []):
            if entry.get("day") == day:
                return list(entry.get("usfm", []))
        return []

    def _verse(self, usfm: str) -> tuple[str, str]:
        """La referencia legible y el texto de un versículo."""
        query = urlencode({"id": NTV, "reference": usfm})
        payload = self.fetch(f"{VERSE_URL}?{query}")
        human = payload["reference"]["human"]
        text = " ".join(payload.get("content", "").split())
        return human, text

    def passage(self) -> Passage | None:
        """El versículo de hoy hablado y escrito, o None si no hay."""
        verses = [self._verse(usfm) for usfm in self.references()]
        text = " ".join(text for _, text in verses if text)
        if not verses or not text:
            return None

        first = _REFERENCE.match(verses[0][0])
        last = _REFERENCE.match(verses[-1][0])
        human = verses[0][0]
        if len(verses) > 1 and first and last:
            human = f"{human}-{last['verse']}"

        written = f"📖 {human} (NTV)\n{text}"
        if first is None or any(character.isdigit() for character in text):
            log.info("el versículo de hoy no se puede decir: %s", human)
            return Passage(spoken="", written=written)

        where = f"capítulo {cardinal(int(first['chapter']))}"
        if len(verses) > 1 and last:
            where += (
                f", versículos {cardinal(int(first['verse']))}"
                f" al {cardinal(int(last['verse']))}"
            )
        else:
            where += f", versículo {cardinal(int(first['verse']))}"
        said = _SHOUTED.sub(lambda word: word[0].capitalize(), text)
        spoken = f"El versículo del día, de {_spoken_book(first['book'])}, {where}: {said}"
        return Passage(spoken=spoken, written=written)

"""The headlines of the day, for the morning summary.

Read straight off the RSS of whichever outlets the house is configured with:
no account, no API key, and the source of every line is known — which is the
reason this is not a model answering "what happened today".

🔴 Written and spoken are different texts, the same split `ask.py` and
`watch.seq.Summary` already make. A headline is made of percentages, prices
and years, and that is exactly what Piper reads as a loose masculine cardinal.
`written` keeps every digit and goes to the chat; `spoken` is the same news
said in words, and it is the only half that reaches the synthesizer.

🔴 If the spoken half cannot be trusted, nothing is said and nothing is lost:
the chat already has the headlines, and the summary points at them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable
from xml.etree import ElementTree

log = logging.getLogger(__name__)

DEFAULT_COUNT = 5
TIMEOUT = 15
# Some outlets answer 403 to a bare client. Clarín is one of them.
USER_AGENT = "Mozilla/5.0 (compatible; domotica/1.0)"

# Five headlines said out loud already run close to a minute of speaker. Past
# this the model stopped saying the news and started narrating it.
MAX_SPOKEN = 900

PROMPT = """Estos son los titulares de hoy, tal como los publicaron los medios.

Decilos en voz alta en español rioplatense, uno por oración, en el mismo orden.
No agregues opinión, contexto, saludos ni comentarios tuyos: solo lo que dice
cada titular, dicho de corrido.
Escribí todos los números con palabras y no uses ni un solo dígito: ni años, ni
porcentajes, ni precios.

Titulares:
{headlines}"""


@dataclass(frozen=True)
class Headline:
    source: str
    title: str


@dataclass(frozen=True)
class Digest:
    """What goes to the chat, and what may be said out loud."""

    written: str
    spoken: str


def fetch_feed(url: str) -> bytes:
    """The real call. Imported lazily so tests never touch the network.

    🔴 The bytes, never `response.text`. Ámbito answers without a charset in
    the header, so requests guesses latin-1 and "Envíos" reaches the chat as
    "EnvÃ­os". The XML declares its own encoding: handing the parser the raw
    bytes is what lets it be believed.
    """
    import requests

    response = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.content


def _titles(body: bytes | str) -> list[str]:
    """Every headline in an RSS channel, in the order the outlet published it."""
    root = ElementTree.fromstring(body)
    found = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        title = " ".join(title.split())
        if title:
            found.append(title)
    return found


class NewsClient:
    def __init__(
        self,
        feeds: dict[str, str],
        fetch: Callable[[str], bytes | str] = fetch_feed,
        speak: Callable[[str], str] | None = None,
        count: int = DEFAULT_COUNT,
        prompt: str = PROMPT,
        max_spoken: int = MAX_SPOKEN,
    ):
        self.feeds = dict(feeds)
        self.fetch = fetch
        # Without a model there is no way to say a headline without digits, so
        # the news stay written. The house is never left saying "mil quinientos
        # treinta y cinco" as "uno cinco tres cinco".
        self.speak = speak
        self.count = count
        self.prompt = prompt
        self.max_spoken = max_spoken

    def headlines(self) -> list[Headline]:
        """The first ones of each outlet, taking turns.

        Taking turns matters: the first five of a single feed are that outlet's
        front page, not the news of the day. A feed that fails leaves its turn
        empty — one outlet down is not the summary down.
        """
        by_source: dict[str, list[str]] = {}
        for alias, url in self.feeds.items():
            try:
                by_source[alias] = _titles(self.fetch(url))
            except Exception as exc:  # noqa: BLE001 - un medio caído no cancela el resto
                log.warning("no pude leer las noticias de %s: %s", alias, exc)

        picked: list[Headline] = []
        for index in range(self.count):
            for alias, titles in by_source.items():
                if index < len(titles):
                    picked.append(Headline(source=alias, title=titles[index]))
                if len(picked) == self.count:
                    return picked
        return picked

    def digest(self) -> Digest:
        picked = self.headlines()
        if not picked:
            return Digest(written="", spoken="")

        written = "\n".join(f"· {line.title} ({line.source})" for line in picked)
        return Digest(written=written, spoken=self._say(picked))

    def _say(self, picked: Iterable[Headline]) -> str:
        if self.speak is None:
            return ""

        listed = "\n".join(f"- {line.title}" for line in picked)
        try:
            answer = self.speak(self.prompt.format(headlines=listed))
        except Exception as exc:  # noqa: BLE001 - sin voz, quedan escritas
            log.warning("no pude poner los titulares en palabras: %s", exc)
            return ""

        answer = (answer or "").strip()
        problem = self._problem_with(answer)
        if problem:
            log.info("los titulares no se dicen (%s): quedan escritos", problem)
            return ""
        return answer

    def _problem_with(self, answer: str) -> str:
        if not answer:
            return "vino vacío"
        if any(character.isdigit() for character in answer):
            return "trae dígitos"
        if len(answer) > self.max_spoken:
            return "se fue de largo"
        return ""

"""Los titulares del día, para el resumen de la mañana.

Salen del RSS de los medios configurados: sin cuenta, sin API key, y de cada
línea se sabe qué medio la publicó. Los titulares se escriben, nunca se dicen:
van al chat tal como los publicó el medio, con dígitos y todo. Nada de acá
habla con un modelo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable
from xml.etree import ElementTree

log = logging.getLogger(__name__)

DEFAULT_COUNT = 5
TIMEOUT = 15
# Algunos medios contestan 403 sin User-Agent. Clarín es uno.
USER_AGENT = "Mozilla/5.0 (compatible; domotica/1.0)"


@dataclass(frozen=True)
class Headline:
    source: str
    title: str


def fetch_feed(url: str) -> bytes:
    """La llamada real. Se importa tarde para que los tests no toquen la red.

    Se leen los bytes, nunca `response.text`: hay medios que contestan sin
    charset en el header y requests adivina latin-1. El XML declara su propio
    encoding.
    """
    import requests

    response = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.content


def _titles(body: bytes | str) -> list[str]:
    """Todos los titulares de un canal RSS, en el orden en que los publicó el medio."""
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
        count: int = DEFAULT_COUNT,
    ):
        self.feeds = dict(feeds)
        self.fetch = fetch
        self.count = count

    def headlines(self) -> list[Headline]:
        """Los primeros de cada medio, tomando turnos.

        Los cinco primeros de un solo diario son su portada, no las noticias
        del día. Un medio caído deja su turno vacío y los otros siguen.
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

    def written(self) -> str:
        """Los titulares tal como los publicaron los medios, o nada."""
        picked = self.headlines()
        if not picked:
            return ""
        return "\n".join(f"· {line.title} ({line.source})" for line in picked)

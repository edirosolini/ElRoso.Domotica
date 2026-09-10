"""The headlines of the day, for the morning summary.

Read straight off the RSS of whichever outlets the house is configured with:
no account, no API key, and the source of every line is known — which is the
reason this is not a model answering "what happened today".

🔴 **The news are written, never spoken.** Decision of the owner, taken after
hearing them: five headlines are the longest thing in the summary and the part
you cannot act on, and they are made of prices, percentages and years — exactly
what the synthesizer reads wrong. They go to the chat as the outlets published
them, digits and all, and the speaker says the rest of the summary.

That is also why nothing here talks to a model. Putting a headline into words
was a whole path — a prompt, a validation, a timeout — that existed only to say
out loud something that is better read.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable
from xml.etree import ElementTree

log = logging.getLogger(__name__)

DEFAULT_COUNT = 5
TIMEOUT = 15
# Some outlets answer 403 to a bare client. Clarín is one of them.
USER_AGENT = "Mozilla/5.0 (compatible; domotica/1.0)"


@dataclass(frozen=True)
class Headline:
    source: str
    title: str


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
        count: int = DEFAULT_COUNT,
    ):
        self.feeds = dict(feeds)
        self.fetch = fetch
        self.count = count

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

    def written(self) -> str:
        """The headlines as the outlets published them, or nothing at all."""
        picked = self.headlines()
        if not picked:
            return ""
        return "\n".join(f"· {line.title} ({line.source})" for line in picked)

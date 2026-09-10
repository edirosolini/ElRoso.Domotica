"""The morning summary: the day ahead, the sky, the figures, and anything broken.

Independent sources joined into one spoken text. Independence is the point: a
calendar that times out must not cost you the weather, the same way a broken
calendar does not hide the others inside the agenda.

Everything spoken here is synthesized, so it carries no digits: the sources
already speak in words and this module only adds names and connectors.

🔴 The news are the one source whose written half is worth more than what is
said: a headline is full of prices and percentages. `speech()` returns both —
the chat gets the headlines as published, the speaker gets them in words — and
when they cannot be said at all, the summary points at the chat instead of
going silent about them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeauto.polish import as_is

log = logging.getLogger(__name__)

NOTHING = "No tengo nada para el resumen de hoy."
NEWS_IN_CHAT = "Las noticias de hoy te las dejé escritas en el chat."


@dataclass(frozen=True)
class Summary:
    """What the house says, and what the chat keeps."""

    spoken: str
    written: str


class Briefing:
    def __init__(
        self,
        agenda=None,
        weather=None,
        monitor=None,
        economy=None,
        news=None,
        polish: Callable[..., str] = as_is,
    ):
        self.agenda = agenda
        self.weather = weather
        self.monitor = monitor
        self.economy = economy
        self.news = news
        # Only the trouble line: the agenda and the weather arrive already
        # reworded by their own sources, and polishing twice buys nothing.
        self.polish = polish

    def text(self) -> str:
        """What the house says at the briefing hour."""
        return self.speech().spoken

    def speech(self) -> Summary:
        """The spoken summary and the copy the chat keeps.

        They only differ when there are news: the headlines go to the chat as
        the outlets published them, digits included.
        """
        parts = [
            said
            for said in (
                self._safe(self._day),
                self._safe(self._sky),
                self._safe(self._money),
                self._safe(self._trouble),
            )
            if said
        ]
        digest = self._safe_digest()
        spoken = list(parts)
        if digest is not None and digest.written:
            spoken.append(digest.spoken or NEWS_IN_CHAT)

        said = " ".join(spoken) if spoken else NOTHING
        if digest is None or not digest.written:
            return Summary(spoken=said, written=said)

        # The written half keeps the summary and adds the headlines under it,
        # so the chat is never a worse copy of what was heard.
        heard = " ".join(parts) if parts else ""
        written = f"{heard}\n\n{digest.written}" if heard else digest.written
        return Summary(spoken=said, written=written)

    @staticmethod
    def _safe(source: Callable[[], str]) -> str:
        try:
            return source()
        except Exception:
            # One source failing is a hole in the summary, not a lost summary.
            log.exception("una fuente del resumen falló")
            return ""

    def _day(self) -> str:
        return self.agenda.briefing() if self.agenda is not None else ""

    def _sky(self) -> str:
        return self.weather.spoken() if self.weather is not None else ""

    def _money(self) -> str:
        return self.economy.spoken() if self.economy is not None else ""

    def _safe_digest(self):
        """The headlines, or None when there are none to be had."""
        if self.news is None:
            return None
        try:
            return self.news.digest()
        except Exception:
            log.exception("no pude traer las noticias")
            return None

    def _trouble(self) -> str:
        """Only what is down. Silence is the good news, and keeps this short."""
        if self.monitor is None:
            return ""

        down = sorted(name for name, state in self.monitor.snapshot().items() if not state.up)
        if not down:
            return ""
        if len(down) == 1:
            text = f"Ojo: {down[0]} no responde."
        else:
            text = f"Ojo: no responden {', '.join(down[:-1])} ni {down[-1]}."
        return self.polish(text, must_keep=tuple(down))

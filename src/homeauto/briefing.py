"""The morning summary: the day ahead, the sky, and anything broken.

Three independent sources joined into one spoken text. Independence is the
point: a calendar that times out must not cost you the weather, the same way a
broken calendar does not hide the others inside the agenda.

Everything here is synthesized, so it carries no digits: the sources already
speak in words and this module only adds names and connectors.
"""

from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger(__name__)

NOTHING = "No tengo nada para el resumen de hoy."


class Briefing:
    def __init__(self, agenda=None, weather=None, monitor=None):
        self.agenda = agenda
        self.weather = weather
        self.monitor = monitor

    def text(self) -> str:
        """What the house says at the briefing hour."""
        parts = [
            said
            for said in (self._safe(self._day), self._safe(self._sky), self._safe(self._trouble))
            if said
        ]
        return " ".join(parts) if parts else NOTHING

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

    def _trouble(self) -> str:
        """Only what is down. Silence is the good news, and keeps this short."""
        if self.monitor is None:
            return ""

        down = sorted(name for name, state in self.monitor.snapshot().items() if not state.up)
        if not down:
            return ""
        if len(down) == 1:
            return f"Ojo: {down[0]} no responde."
        return f"Ojo: no responden {', '.join(down[:-1])} ni {down[-1]}."

"""El cierre del día: lo que viene mañana y lo que sigue roto.

Mismas reglas que el resumen de la mañana —fuentes independientes, una que
falla deja un hueco, nada hablado lleva dígitos— con una diferencia: si no
quedó nada para decir, no se dice nada. A esta hora un cierre vacío es ruido.
"""

from __future__ import annotations

import logging
from typing import Callable

from homeauto.briefing import Summary
from homeauto.lists import SHOPPING
from homeauto.polish import as_is
from homeauto.verbalize import FEMININE, number
from homeauto.watch.monitor import down_line

log = logging.getLogger(__name__)

TOMORROW = "mañana"


class Closing:
    def __init__(
        self,
        agenda=None,
        weather=None,
        monitor=None,
        lists=None,
        polish: Callable[..., str] = as_is,
    ):
        self.agenda = agenda
        self.weather = weather
        self.monitor = monitor
        self.lists = lists
        # Solo la línea de lo caído: la agenda y el clima ya vienen pulidos por
        # sus propias fuentes.
        self.polish = polish

    def text(self) -> str:
        """Lo que la casa dice antes de dormir, o nada si no juntó nada."""
        return self.speech().spoken

    def speech(self) -> Summary:
        """Lo hablado, igual a lo escrito, y la copia sin servicios caídos."""
        tomorrow, sky = self._safe(self._tomorrow), self._safe(self._sky)
        trouble, shopping = self._safe(self._trouble), self._safe(self._shopping)
        said = " ".join(part for part in (tomorrow, sky, trouble, shopping) if part)
        public = " ".join(part for part in (tomorrow, sky, shopping) if part)
        return Summary(spoken=said, written=said, public=public)

    @staticmethod
    def _safe(source: Callable[[], str]) -> str:
        try:
            return source()
        except Exception:
            log.exception("una fuente del cierre del día falló")
            return ""

    def _tomorrow(self) -> str:
        """Lo agendado para mañana, sin el lugar: se escucha de corrido."""
        if self.agenda is None:
            return ""
        return self.agenda.spoken(TOMORROW, place=False)

    def _sky(self) -> str:
        return self.weather.spoken_tomorrow() if self.weather is not None else ""

    def _trouble(self) -> str:
        if self.monitor is None:
            return ""
        return down_line(self.monitor, self.polish)

    def _shopping(self) -> str:
        """Cuántas cosas quedan por comprar. Los ítems se leen, no se escuchan."""
        if self.lists is None:
            return ""

        pending = len(self.lists.items(SHOPPING))
        if not pending:
            return ""
        things = "cosa" if pending == 1 else "cosas"
        return f"En la lista de compras hay {number(pending, FEMININE)} {things}."

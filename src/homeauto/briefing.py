"""El resumen de la mañana: el día, el cielo, las cifras y lo que esté caído.

Fuentes independientes juntadas en un solo texto hablado: una que falla deja un
hueco, nunca cancela el resumen. Nada de lo hablado lleva dígitos. Los
titulares son la única fuente que no se dice, así que `speech()` devuelve las
dos mitades: lo que la casa dice y la copia que queda en el chat.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeauto.polish import as_is
from homeauto.watch.monitor import down_line

log = logging.getLogger(__name__)

NOTHING = "No tengo nada para el resumen de hoy."
# Desde cuándo se miran los errores: la noche entera, hasta la hora del resumen.
NIGHT_HOURS = 12


@dataclass(frozen=True)
class Summary:
    """Lo que dice la casa y lo que queda en el chat."""

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
        seq=(),
        polish: Callable[..., str] = as_is,
    ):
        self.agenda = agenda
        self.weather = weather
        self.monitor = monitor
        self.economy = economy
        # Los errores de la noche: de madrugada no despiertan a nadie, así que
        # se recuerdan acá.
        self.seq = [seq] if hasattr(seq, "errors_since") else list(seq)
        self.news = news
        # Solo la línea de lo caído: la agenda y el clima ya vienen pulidos por
        # sus propias fuentes, y pulir dos veces no agrega nada.
        self.polish = polish

    def text(self) -> str:
        """Lo que la casa dice a la hora del resumen."""
        return self.speech().spoken

    def speech(self) -> Summary:
        """El resumen hablado y la copia que queda en el chat.

        Se diferencian en los titulares, que van solo al chat.
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
        night = self._safe_night()
        if night is not None:
            parts.append(night.spoken)
        said = " ".join(parts) if parts else NOTHING

        written = said
        if night is not None:
            written = f"{written}\n\n{night.detail}"
        headlines = self._safe_news()
        if headlines:
            written = f"{written}\n\n{headlines}"
        return Summary(spoken=said, written=written)

    @staticmethod
    def _safe(source: Callable[[], str]) -> str:
        try:
            return source()
        except Exception:
            # Una fuente que falla es un hueco en el resumen, no un resumen perdido.
            log.exception("una fuente del resumen falló")
            return ""

    def _day(self) -> str:
        return self.agenda.briefing() if self.agenda is not None else ""

    def _sky(self) -> str:
        return self.weather.spoken() if self.weather is not None else ""

    def _money(self) -> str:
        return self.economy.spoken() if self.economy is not None else ""

    def _safe_news(self) -> str:
        """Los titulares para el chat, o nada. Nunca parte de lo hablado."""
        if self.news is None:
            return ""
        try:
            return self.news.written()
        except Exception:
            log.exception("no pude traer las noticias")
            return ""

    def _safe_night(self):
        """Lo que juntó Seq de noche, o None si no hay nada que contar."""
        from datetime import datetime, timedelta

        from homeauto.watch.seq import summarize

        events = []
        for client in self.seq:
            try:
                events.extend(client.errors_since(datetime.now() - timedelta(hours=NIGHT_HOURS)))
            except Exception:
                log.exception("no pude leer los errores de la noche")
        if not events:
            return None

        # Sin "Atención, producción": el fuego ya pasó, esto lo recuerda.
        summary = summarize(events, source="la noche", lead=False)
        if summary is None:
            return None
        spoken = summary.spoken.replace("Hay ", "Anoche hubo ", 1).replace(", en la noche.", ".")
        return type(summary)(spoken=spoken, detail=summary.detail)

    def _trouble(self) -> str:
        """Solo lo caído. El silencio es la buena noticia y mantiene esto corto."""
        if self.monitor is None:
            return ""
        return down_line(self.monitor, self.polish)

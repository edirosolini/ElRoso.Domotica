"""Vigila Seq buscando errores nuevos, sin convertir una tormenta en otra de avisos."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from homeauto.polish import as_is
from homeauto.watch.marks import Marks
from homeauto.watch.seq import summarize

log = logging.getLogger(__name__)

LAST_CHECK = "seq:last_check"
LAST_ALERT = "seq:last_alert"
FIRST_LOOKBACK_MINUTES = 10
COOLDOWN_MINUTES = 15


class SeqWatcher:
    def __init__(
        self,
        client,
        marks: Marks,
        announce: Callable[..., None],
        clock: Callable[[], datetime] = datetime.now,
        cooldown_minutes: int = COOLDOWN_MINUTES,
        lookback_minutes: int = FIRST_LOOKBACK_MINUTES,
        polish: Callable[..., str] = as_is,
        alias: str = "",
    ):
        self.client = client
        self.marks = marks
        self.announce = announce
        self.clock = clock
        self.cooldown_minutes = cooldown_minutes
        self.lookback_minutes = lookback_minutes
        self.polish = polish
        # Vacío para la instancia que estaba primero: sigue diciendo "Seq" y
        # leyendo las marcas que ya escribió.
        self.alias = alias

    @property
    def name(self) -> str:
        """Cómo se lo nombra en voz alta.

        Los guiones bajos se dicen como espacios: son el separador que impone el
        nombre de una variable de entorno.
        """
        return f"Seq de {self.alias.replace('_', ' ')}" if self.alias else "Seq"

    @property
    def last_check_key(self) -> str:
        return f"seq:{self.alias}:last_check" if self.alias else LAST_CHECK

    @property
    def last_alert_key(self) -> str:
        # Un enfriamiento por instancia: un VPS ruidoso no puede callar al otro.
        return f"seq:{self.alias}:last_alert" if self.alias else LAST_ALERT

    def check(self) -> str | None:
        now = self.clock()
        since = self.marks.get(self.last_check_key) or now - timedelta(minutes=self.lookback_minutes)

        try:
            events = self.client.errors_since(since)
        except Exception as exc:  # noqa: BLE001 - el loop no puede morirse por esto
            log.warning("no pude leer Seq: %s", exc)
            return None

        self.marks.set(self.last_check_key, now)
        if not events:
            return None

        # Un servicio roto loguea el mismo error cientos de veces por minuto.
        last_alert = self.marks.get(self.last_alert_key)
        if last_alert and now - last_alert < timedelta(minutes=self.cooldown_minutes):
            log.info("hay errores en Seq pero seguimos en enfriamiento")
            return None

        summary = summarize(events, source=self.name)
        if summary is None:
            return None

        # La cita del log queda escrita: es texto arbitrario, con dígitos y
        # trazas, y nada de eso sobrevive al ser dicho.
        spoken = self.polish(summary.spoken, must_keep=("Seq", self.alias))
        self.announce(spoken, summary.detail)
        self.marks.set(self.last_alert_key, now)
        return spoken

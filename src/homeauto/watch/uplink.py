"""Vigila la salida a internet de la casa y avisa cuando se corta y cuando vuelve."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from homeauto.verbalize import duration
from homeauto.watch.checks import tcp_connect
from homeauto.watch.marks import Marks

log = logging.getLogger(__name__)

TARGETS = (("1.1.1.1", 443), ("8.8.8.8", 443), ("9.9.9.9", 443))
TIMEOUT = 3
DOWN_SINCE = "uplink:down_since"
ALERTED = "uplink:alerted"


class Uplink:
    def __init__(
        self,
        marks: Marks,
        speak: Callable[[str], None],
        tell: Callable[[str], None],
        connect: Callable[[str, int, int], float] = tcp_connect,
        clock: Callable[[], datetime] = datetime.now,
        targets: tuple[tuple[str, int], ...] = TARGETS,
        timeout: int = TIMEOUT,
    ):
        self.marks = marks
        self.speak = speak
        self.tell = tell
        self.connect = connect
        self.clock = clock
        self.targets = targets
        self.timeout = timeout
        # Resultado de la última ronda; antes de la primera se da por arriba.
        self.online = True

    def reachable(self) -> bool:
        """Si contesta al menos uno de los destinos."""
        for host, port in self.targets:
            try:
                self.connect(host, port, self.timeout)
                return True
            except Exception as exc:  # noqa: BLE001 - cualquier fallo es "no contesta"
                log.debug("uplink target %s:%s unreachable: %s", host, port, exc)
        return False

    def run_once(self) -> bool:
        """Una ronda: prueba los destinos, actualiza el estado y avisa si cambió. Devuelve si hay internet."""
        now = self.clock()
        self.online = self.reachable()
        down_since = self.marks.get(DOWN_SINCE)

        if self.online:
            if down_since is not None:
                self._back(down_since, now)
            return True

        if down_since is None:
            log.info("uplink: no target answered")
            self.marks.set(DOWN_SINCE, now)
        elif self.marks.get(ALERTED) is None:
            log.warning("uplink down since %s", down_since)
            self.marks.set(ALERTED, now)
            self._safely(self.speak, "Se cortó internet.")
        return False

    def _back(self, down_since: datetime, now: datetime) -> None:
        """Cierra el corte; si se había declarado, dice y escribe cuánto duró."""
        alerted = self.marks.get(ALERTED) is not None
        self.marks.clear(DOWN_SINCE)
        self.marks.clear(ALERTED)
        if not alerted:
            return
        minutes = max(1, round((now - down_since).total_seconds() / 60))
        log.info("uplink back after %s minutes", minutes)
        self._safely(self.speak, f"Volvió internet. Estuvo cortado {duration(minutes)}.")
        self._safely(
            self.tell,
            f"🌐 Internet se cortó de {down_since:%H:%M} a {now:%H:%M} ({minutes} min)",
        )

    @staticmethod
    def _safely(send: Callable[[str], None], text: str) -> None:
        """Manda `text` sin que una falla corte la ronda."""
        try:
            send(text)
        except Exception:
            log.exception("could not deliver uplink notice")

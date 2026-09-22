"""Vigilancia de servicios externos, sin volverse ruido.

Solo habla cuando algo *cambia*, y aguanta dos fallos seguidos antes de
declarar una caída.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from homeauto.polish import as_is
from homeauto.watch.checks import Check, HttpProbe, TcpProbe, run_check
from homeauto.watch.status import Status, StatusStore

log = logging.getLogger(__name__)

FAILURES_TO_DECLARE = 2


def down_line(monitor, polish: Callable[..., str] = as_is) -> str:
    """Los servicios caídos en una oración, o nada si están todos en pie.

    El silencio es la buena noticia: el estado completo está en `/estado`.
    """
    down = sorted(name for name, state in monitor.snapshot().items() if not state.up)
    if not down:
        return ""
    if len(down) == 1:
        text = f"Ojo: {down[0]} no responde."
    else:
        text = f"Ojo: no responden {', '.join(down[:-1])} ni {down[-1]}."
    return polish(text, must_keep=tuple(down))


class Monitor:
    def __init__(
        self,
        checks: list[Check],
        store: StatusStore,
        announce: Callable[[str, bool], None],
        run: Callable = run_check,
        http: HttpProbe | None = None,
        tcp: TcpProbe | None = None,
        clock: Callable[[], datetime] = datetime.now,
        failures_to_declare: int = FAILURES_TO_DECLARE,
        polish: Callable[..., str] = as_is,
    ):
        self.checks = checks
        self.store = store
        self.announce = announce
        self.run = run
        self.http = http or HttpProbe()
        self.tcp = tcp or TcpProbe()
        self.clock = clock
        self.failures_to_declare = failures_to_declare
        self.polish = polish

    def snapshot(self) -> dict[str, Status]:
        """El estado de lo que se vigila *ahora*.

        Filtrado por los chequeos configurados, no por la tabla entera: un
        chequeo renombrado deja una fila que nadie va a volver a chequear.
        """
        watched = {check.name for check in self.checks}
        return {name: state for name, state in self.store.all().items() if name in watched}

    def run_once(self) -> list[str]:
        now = self.clock()
        announced = []

        for check in self.checks:
            try:
                result = self.run(check, http=self.http, tcp=self.tcp)
            except Exception:  # noqa: BLE001 - el loop no puede morirse por un chequeo
                log.exception("falló el chequeo de %s", check.name)
                continue

            previous = self.store.get(check.name)
            message = self._advance(check, result, previous, now)
            if message:
                announced.append(message)

        return announced

    def _say(self, text: str, name: str) -> str:
        """La mitad hablada, pulida. El detalle de la sonda no llega acá: lleva
        un estado HTTP y una duración, y un dígito se lee mal."""
        return self.polish(text, must_keep=(name,))

    def _advance(self, check: Check, result, previous: Status | None, now: datetime) -> str | None:
        was_alerted = previous.alerted if previous else False
        failures = previous.failures if previous else 0

        if result.up:
            # Solo vale contarlo si alguien se enteró de la caída.
            message = None
            if was_alerted:
                message = self._say(f"{check.name} volvió a responder.", check.name)
                self.announce(message, False, result.detail)
            self.store.save(Status(check.name, True, 0, False, result.detail, now))
            return message

        failures += 1
        message = None
        if not was_alerted and failures >= self.failures_to_declare:
            message = self._say(f"Atención: {check.name} no responde.", check.name)
            self.announce(message, result.urgent, result.detail)
            was_alerted = True

        self.store.save(Status(check.name, False, failures, was_alerted, result.detail, now))
        return message

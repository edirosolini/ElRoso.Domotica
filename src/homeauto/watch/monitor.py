"""Watching external services without becoming noise.

Two rules decide everything here: it only speaks when something *changes*, and
it waits for a couple of consecutive failures before calling it an outage. A
monitor that cries at every timeout teaches you to ignore it, which is worse
than having no monitor at all.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from homeauto.watch.checks import Check, HttpProbe, TcpProbe, run_check
from homeauto.watch.status import Status, StatusStore

log = logging.getLogger(__name__)

FAILURES_TO_DECLARE = 2


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
    ):
        self.checks = checks
        self.store = store
        self.announce = announce
        self.run = run
        self.http = http or HttpProbe()
        self.tcp = tcp or TcpProbe()
        self.clock = clock
        self.failures_to_declare = failures_to_declare

    def snapshot(self) -> dict[str, Status]:
        return self.store.all()

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

    def _advance(self, check: Check, result, previous: Status | None, now: datetime) -> str | None:
        was_alerted = previous.alerted if previous else False
        failures = previous.failures if previous else 0

        if result.up:
            # Only worth telling if somebody was told about the outage.
            message = None
            if was_alerted:
                message = f"{check.name} volvió a responder. {result.detail}"
                self.announce(message, False)
            self.store.save(Status(check.name, True, 0, False, result.detail, now))
            return message

        failures += 1
        message = None
        if not was_alerted and failures >= self.failures_to_declare:
            message = f"Atención: {check.name} no responde. {result.detail}"
            self.announce(message, result.urgent)
            was_alerted = True

        self.store.save(Status(check.name, False, failures, was_alerted, result.detail, now))
        return message

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

from homeauto.polish import as_is
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
        """The state of what is being watched *now*.

        🔴 Filtered by the configured checks, not the whole table. Renaming or
        dropping a check leaves its old row behind, and nothing ever checks it
        again: it would sit in `/estado` red forever, a recovery that can never
        arrive. A monitor showing an outage that no longer exists teaches you
        to stop reading it.
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
        """The spoken half, reworded. The probe detail never gets here: it
        carries an HTTP status and a duration, and a digit is read wrong."""
        return self.polish(text, must_keep=(name,))

    def _advance(self, check: Check, result, previous: Status | None, now: datetime) -> str | None:
        was_alerted = previous.alerted if previous else False
        failures = previous.failures if previous else 0

        if result.up:
            # Only worth telling if somebody was told about the outage.
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

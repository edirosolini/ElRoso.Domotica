"""Watching Seq for new errors, without turning a storm into a storm of alerts."""

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
    ):
        self.client = client
        self.marks = marks
        self.announce = announce
        self.clock = clock
        self.cooldown_minutes = cooldown_minutes
        self.lookback_minutes = lookback_minutes
        self.polish = polish

    def check(self) -> str | None:
        now = self.clock()
        since = self.marks.get(LAST_CHECK) or now - timedelta(minutes=self.lookback_minutes)

        try:
            events = self.client.errors_since(since)
        except Exception as exc:  # noqa: BLE001 - el loop no puede morirse por esto
            log.warning("no pude leer Seq: %s", exc)
            return None

        self.marks.set(LAST_CHECK, now)
        if not events:
            return None

        # A failing service logs the same error hundreds of times a minute.
        # Alerting on each one turns the monitor into noise.
        last_alert = self.marks.get(LAST_ALERT)
        if last_alert and now - last_alert < timedelta(minutes=self.cooldown_minutes):
            log.info("hay errores en Seq pero seguimos en enfriamiento")
            return None

        summary = summarize(events)
        if summary is None:
            return None

        # The quoted log line stays written: it is arbitrary text, with digits
        # and stack traces in it, and none of that survives being spoken.
        spoken = self.polish(summary.spoken, must_keep=("Seq",))
        self.announce(spoken, summary.detail)
        self.marks.set(LAST_ALERT, now)
        return spoken

"""Reading errors out of Seq.

Seq holds the logs of the services running on the VPS, so it answers *why*
something broke instead of just that it stopped answering. It cannot report the
VPS being down — it dies with it — which is why the tunnel is watched
separately as a plain TCP check.

⚠️ The exact field names of this Seq instance were not verified against the
real API (it needs a key). The parser is deliberately tolerant: it accepts the
documented names and a couple of likely variants, and never crashes on a
missing field.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from homeauto.verbalize import number

log = logging.getLogger(__name__)

TIMEOUT = 15
MAX_EVENTS = 50
QUOTE_LIMIT = 200
ERROR_FILTER = "@Level in ['Error', 'Fatal']"

MESSAGE_FIELDS = ("RenderedMessage", "Message", "MessageTemplate", "@m")
LEVEL_FIELDS = ("Level", "@l")
TIME_FIELDS = ("Timestamp", "@t")


class SeqError(Exception):
    """Seq could not be queried."""


@dataclass(frozen=True)
class SeqEvent:
    timestamp: datetime | None
    level: str
    message: str


def _first(payload: dict, names: tuple[str, ...], default=None):
    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return value
    return default


def http_get(url: str, headers: dict, params: dict) -> tuple[int, object]:
    import requests

    response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
    if response.status_code != 200:
        return response.status_code, None
    return response.status_code, response.json()


class SeqClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        fetch: Callable[[str, dict, dict], tuple[int, object]] = http_get,
        count: int = MAX_EVENTS,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.fetch = fetch
        self.count = count

    def errors_since(self, since: datetime) -> list[SeqEvent]:
        params = {
            "filter": ERROR_FILTER,
            "count": self.count,
            "fromDateUtc": since.astimezone().isoformat(),
            "render": "true",
        }
        try:
            status, payload = self.fetch(
                f"{self.base_url}/api/events",
                {"X-Seq-ApiKey": self.api_key, "Accept": "application/json"},
                params,
            )
        except Exception as exc:  # noqa: BLE001
            raise SeqError(f"no pude consultar Seq: {exc}") from exc

        if status == 401 or status == 403:
            raise SeqError("Seq rechazó la clave de API")
        if status != 200:
            raise SeqError(f"Seq contestó HTTP {status}")
        if not isinstance(payload, list):
            raise SeqError("Seq contestó algo que no es una lista de eventos")

        return [self._to_event(item) for item in payload if isinstance(item, dict)]

    @staticmethod
    def _to_event(payload: dict) -> SeqEvent:
        raw_time = _first(payload, TIME_FIELDS)
        moment = None
        if raw_time:
            try:
                moment = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            except ValueError:
                moment = None

        return SeqEvent(
            timestamp=moment,
            level=str(_first(payload, LEVEL_FIELDS, "Error")),
            message=str(_first(payload, MESSAGE_FIELDS, "(evento sin mensaje)")),
        )


@dataclass(frozen=True)
class Summary:
    """What gets said out loud, and what only gets written.

    🔴 They are separate because the quoted log line is arbitrary text: it
    carries stack traces, ids and digits, and Piper reads a digit as a loose
    masculine cardinal. The count is spelled out for the same reason — "Hay 1
    error" was said as "hay uno error".
    """

    spoken: str
    detail: str


def summarize(events: list[SeqEvent]) -> Summary | None:
    """One sentence out loud. Reading seven stack traces helps nobody."""
    if not events:
        return None

    count = len(events)
    thing = "error nuevo" if count == 1 else "errores nuevos"
    heading = f"Hay {number(count)} {thing} en Seq."

    latest = max(events, key=lambda e: (e.timestamp is not None, e.timestamp or 0))
    quote = latest.message.strip().replace("\n", " ")
    if len(quote) > QUOTE_LIMIT:
        quote = quote[:QUOTE_LIMIT].rstrip() + "…"

    return Summary(spoken=heading, detail=f"El último: {quote}")

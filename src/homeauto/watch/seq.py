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
APP_PROPERTIES = ("ApplicationName", "Application", "App")
ENV_PROPERTIES = ("EnvironmentName", "Environment", "ASPNETCORE_ENVIRONMENT")

# Cómo se dice cada ambiente. El valor crudo va al chat; esto va al parlante.
SPOKEN_ENVIRONMENTS = {
    "production": "producción",
    "produccion": "producción",
    "prod": "producción",
    "staging": "pruebas",
    "stage": "pruebas",
    "testing": "pruebas",
    "test": "pruebas",
    "qa": "pruebas",
    "development": "desarrollo",
    "dev": "desarrollo",
    "local": "desarrollo",
}
PRODUCTION = "producción"
# Cuántos grupos se nombran en voz alta antes de resumir el resto.
SPOKEN_GROUPS = 2


class SeqError(Exception):
    """Seq could not be queried."""


@dataclass(frozen=True)
class SeqEvent:
    timestamp: datetime | None
    level: str
    message: str
    # Un mismo servidor corre varias apps y varios ambientes: sin esto el aviso
    # no dice si hay que salir corriendo.
    application: str = ""
    environment: str = ""


def _first(payload: dict, names: tuple[str, ...], default=None):
    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return value
    return default


def _properties(payload: dict) -> dict:
    """The event properties as a plain dict; Seq sends them as a list of pairs."""
    found = {}
    for item in payload.get("Properties") or []:
        if isinstance(item, dict) and item.get("Name"):
            found[item["Name"]] = item.get("Value")
    return found


def spoken_environment(raw: str) -> str:
    """How an environment is said out loud."""
    clean = raw.strip().lower()
    return SPOKEN_ENVIRONMENTS.get(clean, clean.replace("-", " ").replace("_", " "))


def spoken_application(raw: str, environment: str = "") -> str:
    """The app name without what Piper reads wrong.

    "Staging-Facturador.Backend" carries the environment as a prefix and reads
    as "staging guion facturador punto backend".
    """
    name = raw.strip()
    prefix = f"{environment.strip()}-"
    if environment and name.lower().startswith(prefix.lower()):
        name = name[len(prefix):]
    return name.replace(".", " ").replace("-", " ").replace("_", " ").strip()


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

        properties = _properties(payload)
        return SeqEvent(
            timestamp=moment,
            level=str(_first(payload, LEVEL_FIELDS, "Error")),
            message=str(_first(payload, MESSAGE_FIELDS, "(evento sin mensaje)")),
            application=str(_first(properties, APP_PROPERTIES, "") or ""),
            environment=str(_first(properties, ENV_PROPERTIES, "") or ""),
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


def _group(events: list[SeqEvent]) -> list[tuple[str, str, int]]:
    """(environment, application, count), production first, then by count."""
    counted: dict[tuple[str, str], int] = {}
    for event in events:
        key = (event.environment, event.application)
        counted[key] = counted.get(key, 0) + 1

    def rank(item):
        (environment, _application), count = item
        return (spoken_environment(environment) != PRODUCTION, -count)

    return [(env, app, count) for (env, app), count in sorted(counted.items(), key=rank)]


def _phrase(environment: str, application: str, count: int, with_environment: bool) -> str:
    thing = "error nuevo" if count == 1 else "errores nuevos"
    said = f"{number(count)} {thing}"
    app = spoken_application(application, environment)
    if app:
        said += f" en {app}"
    env = spoken_environment(environment)
    if env and with_environment:
        said += f" de {env}"
    return said


def summarize(events: list[SeqEvent], source: str = "Seq", lead: bool = True) -> Summary | None:
    """One sentence out loud. Reading seven stack traces helps nobody.

    `source` names which Seq it is; the environment and the app say whether it
    is a fire or somebody testing. `lead` is the "Atención, producción" in
    front: the morning summary remembers what happened, it does not alert.
    """
    if not events:
        return None

    groups = _group(events)
    on_fire = lead and any(
        spoken_environment(environment) == PRODUCTION for environment, _, _ in groups
    )
    # Con un solo grupo de producción, "Atención, producción" ya lo dijo.
    with_environment = len(groups) > 1 or not on_fire

    said = [
        _phrase(environment, app, count, with_environment)
        for environment, app, count in groups[:SPOKEN_GROUPS]
    ]
    rest = len(groups) - len(said)
    if rest > 0:
        said.append(f"{number(rest, 'f')} {'aplicación más' if rest == 1 else 'aplicaciones más'}")

    listed = said[0] if len(said) == 1 else ", ".join(said[:-1]) + " y " + said[-1]
    heading = f"Hay {listed}, en {source}."
    if on_fire:
        heading = f"Atención, producción. {heading}"

    latest = max(events, key=lambda e: (e.timestamp is not None, e.timestamp or 0))
    quote = latest.message.strip().replace("\n", " ")
    if len(quote) > QUOTE_LIMIT:
        quote = quote[:QUOTE_LIMIT].rstrip() + "…"

    lines = [f"{source}:"]
    for environment, application, count in groups:
        where = " · ".join(part for part in (environment, application) if part)
        if not where:
            mark, where = "❔", "sin identificar"
        else:
            mark = "🔥" if spoken_environment(environment) == PRODUCTION else "🧪"
        lines.append(f"{mark} {where}: {count}")
    lines.append(f"El último: {quote}")

    return Summary(spoken=heading, detail="\n".join(lines))

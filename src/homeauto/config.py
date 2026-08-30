"""Loading and validation of the service environment file."""

from __future__ import annotations

import re
import uuid
from datetime import time as clock_time

from homeauto.quiet import QuietHours
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    """The environment file is missing, incomplete or malformed."""


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _read_pairs(path: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        pairs[key.strip()] = _unquote(value.strip())
    return pairs


ALIAS_SHAPE = re.compile(r"^[a-z0-9_-]{1,20}$")

# Buenos Aires: sirve para que el clima funcione sin configurar nada.
DEFAULT_LAT = -34.6037
DEFAULT_LON = -58.3816

# La casa duerme: por defecto, de 23 a 7 nada suena en voz alta.
DEFAULT_QUIET_FROM = "23:00"
DEFAULT_QUIET_TO = "07:00"

# Un token corto se adivina; si es débil, mejor no arrancar.
MIN_TOKEN_LENGTH = 16
DEFAULT_API_PORT = 8099

# El resumen del día y el aviso previo a cada evento.
DEFAULT_BRIEFING_AT = "08:00"
DEFAULT_EVENT_LEAD = 10
CALENDAR_PREFIX = "CALENDAR_URL_"


def _parse_coordinate(raw: str, key: str, default: float, limit: float) -> float:
    raw = raw.strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} no es un número: {raw}") from exc
    if not -limit <= value <= limit:
        raise ConfigError(f"{key} fuera de rango: {value}")
    return value


def _parse_devices(raw: str) -> dict[str, uuid.UUID]:
    """`alias:uuid, alias:uuid` into an ordered mapping. Order sets the default."""
    devices: dict[str, uuid.UUID] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        alias, separator, raw_uuid = chunk.partition(":")
        if not separator:
            raise ConfigError(f"CAST_DEVICES: '{chunk}' no tiene forma alias:uuid")

        alias = alias.strip().lower()
        if not ALIAS_SHAPE.fullmatch(alias):
            raise ConfigError(
                f"CAST_DEVICES: '{alias}' no sirve como alias "
                "(letras, números, guiones, sin espacios)"
            )
        if alias in devices:
            raise ConfigError(f"CAST_DEVICES: alias repetido '{alias}'")

        try:
            devices[alias] = uuid.UUID(raw_uuid.strip())
        except ValueError as exc:
            raise ConfigError(f"CAST_DEVICES: el uuid de '{alias}' no es válido") from exc
    return devices


def _parse_calendars(pairs: dict[str, str]) -> dict[str, str]:
    """One key per calendar.

    A comma-separated `alias:url` list would be ambiguous: the URLs carry
    colons and slashes of their own, and that is where silly bugs live.
    """
    calendars: dict[str, str] = {}
    for key, value in pairs.items():
        url = value.strip()
        if key == "CALENDAR_URL" and url:
            calendars["agenda"] = url
        elif key.startswith(CALENDAR_PREFIX) and url:
            calendars[key[len(CALENDAR_PREFIX):].strip().lower()] = url

    for alias, url in calendars.items():
        if not url.startswith(("http://", "https://")):
            key = "CALENDAR_URL" if alias == "agenda" else f"{CALENDAR_PREFIX}{alias.upper()}"
            raise ConfigError(f"{key} tiene que ser una URL http(s)")
    return calendars


def _parse_briefing(pairs: dict[str, str]) -> clock_time | None:
    raw = pairs.get("BRIEFING_AT", "").strip() or DEFAULT_BRIEFING_AT
    if raw.lower() in ("off", "no", "0"):
        return None
    try:
        hour, _, minute = raw.partition(":")
        return clock_time(int(hour), int(minute or 0))
    except ValueError as exc:
        raise ConfigError(f"BRIEFING_AT no es una hora válida: {raw}") from exc


def _parse_lead(pairs: dict[str, str]) -> int:
    raw = pairs.get("EVENT_LEAD_MINUTES", "").strip()
    if not raw:
        return DEFAULT_EVENT_LEAD
    try:
        minutes = int(raw)
    except ValueError as exc:
        raise ConfigError(f"EVENT_LEAD_MINUTES no es un número: {raw}") from exc
    if not 1 <= minutes <= 180:
        raise ConfigError(f"EVENT_LEAD_MINUTES fuera de rango: {minutes}")
    return minutes


def _parse_api_token(pairs: dict[str, str]) -> str:
    token = pairs.get("API_TOKEN", "").strip()
    if token and len(token) < MIN_TOKEN_LENGTH:
        raise ConfigError(f"API_TOKEN es muy corto (mínimo {MIN_TOKEN_LENGTH} caracteres)")
    return token


def _parse_api_port(pairs: dict[str, str]) -> int:
    raw = pairs.get("API_PORT", "").strip()
    if not raw:
        return DEFAULT_API_PORT
    try:
        port = int(raw)
    except ValueError as exc:
        raise ConfigError(f"API_PORT no es un número: {raw}") from exc
    if not 1 <= port <= 65535:
        raise ConfigError(f"API_PORT fuera de rango: {port}")
    return port


def _parse_quiet(pairs: dict[str, str]) -> QuietHours:
    start = pairs.get("QUIET_FROM", "").strip() or DEFAULT_QUIET_FROM
    end = pairs.get("QUIET_TO", "").strip() or DEFAULT_QUIET_TO
    try:
        return QuietHours.parse(start, end)
    except ValueError as exc:
        raise ConfigError(f"QUIET_FROM/QUIET_TO: {exc}") from exc


def _parse_chat_ids(raw: str) -> frozenset[int]:
    ids = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.add(int(chunk))
        except ValueError as exc:
            raise ConfigError(f"ALLOWED_CHAT_IDS: '{chunk}' no es un número") from exc
    return frozenset(ids)


@dataclass(frozen=True)
class Config:
    """Runtime configuration read from the environment file."""

    telegram_token: str
    devices: dict[str, uuid.UUID]
    default_device: str
    allowed_chat_ids: frozenset[int]
    weather_lat: float = DEFAULT_LAT
    weather_lon: float = DEFAULT_LON
    weather_place: str = ""
    quiet_hours: QuietHours = QuietHours.parse(DEFAULT_QUIET_FROM, DEFAULT_QUIET_TO)
    api_token: str = ""
    api_port: int = DEFAULT_API_PORT
    calendars: dict[str, str] = field(default_factory=dict)
    briefing_at: clock_time | None = None
    event_lead_minutes: int = DEFAULT_EVENT_LEAD

    @classmethod
    def from_file(cls, path: Path | str) -> "Config":
        path = Path(path)
        if not path.is_file():
            raise ConfigError(f"El archivo de configuración no existe: {path}")

        pairs = _read_pairs(path)

        token = pairs.get("TELEGRAM_TOKEN", "").strip()
        if not token:
            raise ConfigError("TELEGRAM_TOKEN está vacío o ausente")

        raw_devices = pairs.get("CAST_DEVICES", "").strip()
        if raw_devices:
            devices = _parse_devices(raw_devices)
        else:
            # Older deployments carried a single CAST_UUID; keep them working.
            legacy = pairs.get("CAST_UUID", "").strip()
            if not legacy:
                raise ConfigError("Falta CAST_DEVICES (alias:uuid, separados por coma)")
            try:
                devices = {"parlante": uuid.UUID(legacy)}
            except ValueError as exc:
                raise ConfigError(f"CAST_UUID no es un UUID válido: {legacy}") from exc

        if not devices:
            raise ConfigError("CAST_DEVICES no tiene ningún dispositivo")

        default = pairs.get("CAST_DEFAULT", "").strip().lower() or next(iter(devices))
        if default not in devices:
            raise ConfigError(f"CAST_DEFAULT apunta a '{default}', que no está en CAST_DEVICES")

        return cls(
            telegram_token=token,
            devices=devices,
            default_device=default,
            allowed_chat_ids=_parse_chat_ids(pairs.get("ALLOWED_CHAT_IDS", "")),
            weather_lat=_parse_coordinate(pairs.get("WEATHER_LAT", ""), "WEATHER_LAT", DEFAULT_LAT, 90),
            weather_lon=_parse_coordinate(pairs.get("WEATHER_LON", ""), "WEATHER_LON", DEFAULT_LON, 180),
            weather_place=pairs.get("WEATHER_PLACE", "").strip(),
            quiet_hours=_parse_quiet(pairs),
            api_token=_parse_api_token(pairs),
            api_port=_parse_api_port(pairs),
            calendars=_parse_calendars(pairs),
            briefing_at=_parse_briefing(pairs),
            event_lead_minutes=_parse_lead(pairs),
        )

    @property
    def cast_uuid(self) -> uuid.UUID:
        """The default device, for everything that only ever needs one."""
        return self.devices[self.default_device]

    @property
    def api_enabled(self) -> bool:
        return bool(self.api_token)

    @property
    def calendar_enabled(self) -> bool:
        return bool(self.calendars)

    def has_device(self, alias: str) -> bool:
        return alias.strip().lower() in self.devices

    def uuid_for(self, alias: str) -> uuid.UUID:
        return self.devices[alias.strip().lower()]

    @property
    def is_open_enrollment(self) -> bool:
        """No whitelist yet: the bot is waiting for its first owner to show up."""
        return not self.allowed_chat_ids

    def is_allowed(self, chat_id: int) -> bool:
        return self.is_open_enrollment or chat_id in self.allowed_chat_ids

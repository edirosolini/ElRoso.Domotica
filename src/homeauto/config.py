"""Loading and validation of the service environment file."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
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
    cast_uuid: uuid.UUID
    allowed_chat_ids: frozenset[int]

    @classmethod
    def from_file(cls, path: Path | str) -> "Config":
        path = Path(path)
        if not path.is_file():
            raise ConfigError(f"El archivo de configuración no existe: {path}")

        pairs = _read_pairs(path)

        token = pairs.get("TELEGRAM_TOKEN", "").strip()
        if not token:
            raise ConfigError("TELEGRAM_TOKEN está vacío o ausente")

        raw_uuid = pairs.get("CAST_UUID", "").strip()
        if not raw_uuid:
            raise ConfigError("CAST_UUID está vacío o ausente")
        try:
            cast_uuid = uuid.UUID(raw_uuid)
        except ValueError as exc:
            raise ConfigError(f"CAST_UUID no es un UUID válido: {raw_uuid}") from exc

        return cls(
            telegram_token=token,
            cast_uuid=cast_uuid,
            allowed_chat_ids=_parse_chat_ids(pairs.get("ALLOWED_CHAT_IDS", "")),
        )

    @property
    def is_open_enrollment(self) -> bool:
        """No whitelist yet: the bot is waiting for its first owner to show up."""
        return not self.allowed_chat_ids

    def is_allowed(self, chat_id: int) -> bool:
        return self.is_open_enrollment or chat_id in self.allowed_chat_ids

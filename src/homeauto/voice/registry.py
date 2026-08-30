"""One speaker per configured device, built the first time it is needed.

Connecting to a cast device is slow, so the objects are cached; and nothing is
built at startup, because most of the devices are usually off.
"""

from __future__ import annotations

import uuid
from typing import Callable


class UnknownDevice(Exception):
    """The alias does not match any configured device."""


class SpeakerRegistry:
    def __init__(self, devices: dict[str, uuid.UUID], build: Callable[[uuid.UUID], object]):
        self._devices = dict(devices)
        self._build = build
        self._cache: dict[str, object] = {}

    @property
    def aliases(self) -> list[str]:
        return list(self._devices)

    def has(self, alias: str) -> bool:
        return alias.strip().lower() in self._devices

    def get(self, alias: str):
        alias = alias.strip().lower()
        if alias not in self._devices:
            known = ", ".join(self._devices) or "ninguno"
            raise UnknownDevice(f"No conozco '{alias}'. Tengo: {known}")

        if alias not in self._cache:
            self._cache[alias] = self._build(self._devices[alias])
        return self._cache[alias]

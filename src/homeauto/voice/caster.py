"""Control of a Google cast device.

The device is looked up by **UUID and never by IP**: these speakers take their
address from DHCP and do move. `catt` is deliberately not used here — it fails
to play local files; pychromecast driven directly works.
"""

from __future__ import annotations

import uuid as uuidlib
from typing import Callable

DISCOVERY_TIMEOUT = 20
AUDIO_MIME = "audio/wav"


class CastError(Exception):
    """The device could not be reached, or was asked for something invalid."""


def discover_devices(timeout: int = DISCOVERY_TIMEOUT) -> list:
    """Real mDNS discovery. Imported lazily so tests never touch the network."""
    import pychromecast

    casts, browser = pychromecast.get_chromecasts(timeout=timeout)
    browser.stop_discovery()
    return casts


class Caster:
    """Plays audio on one cast device, resolved by UUID."""

    def __init__(
        self,
        device_uuid: uuidlib.UUID,
        discover: Callable[..., list] = discover_devices,
        discovery_timeout: int = DISCOVERY_TIMEOUT,
    ):
        self.device_uuid = device_uuid
        self.discover = discover
        self.discovery_timeout = discovery_timeout
        self._device = None

    def _resolve(self):
        if self._device is not None:
            return self._device

        found = self.discover(timeout=self.discovery_timeout)
        for candidate in found:
            if candidate.cast_info.uuid == self.device_uuid:
                candidate.wait(timeout=self.discovery_timeout)
                self._device = candidate
                return candidate

        seen = ", ".join(getattr(c.cast_info, "friendly_name", "?") for c in found) or "ninguno"
        raise CastError(f"No encontré el dispositivo {self.device_uuid}. Vi: {seen}")

    def forget(self) -> None:
        """Drop the cached device so the next call rediscovers it."""
        self._device = None

    def device_name(self) -> str:
        return self._resolve().cast_info.friendly_name

    def play(self, url: str) -> None:
        controller = self._resolve().media_controller
        controller.play_media(url, AUDIO_MIME)
        controller.block_until_active(timeout=self.discovery_timeout)

    def set_volume(self, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise CastError("El volumen tiene que estar entre 0 y 100")
        self._resolve().set_volume(percent / 100)

    def stop(self) -> None:
        self._resolve().media_controller.stop()

"""Control of a Google cast device.

The device is looked up by **UUID and never by IP**: these speakers take their
address from DHCP and do move. `catt` is deliberately not used here — it fails
to play local files; pychromecast driven directly works.
"""

from __future__ import annotations

import logging
import time
import uuid as uuidlib
from typing import Callable

log = logging.getLogger(__name__)

DISCOVERY_TIMEOUT = 20
AUDIO_MIME = "audio/wav"

# Google's Default Media Receiver: the app our own playback runs in.
MEDIA_RECEIVER_APP_ID = "CC1AD845"

PLAYBACK_TIMEOUT = 20
# Waiting for the clip to *end* is a different job from waiting for it to
# start: the briefing runs well past twenty seconds, and cutting the volume
# back mid-sentence is exactly what the floor was meant to prevent. The real
# bound is the length of the audio, which we know; this is only the cap for
# when it could not be read, so a wedged device never holds the thread for good.
FINISH_TIMEOUT = 120
# Margin over the clip length: the device starts a moment after we ask.
FINISH_MARGIN = 5
SETTLE_AFTER_QUIT = 2


class CastError(Exception):
    """The device could not be reached, or was asked for something invalid."""


class _Discovery:
    """Real mDNS discovery. Imported lazily so tests never touch the network.

    🔴 The zeroconf browser is deliberately kept alive. pychromecast needs it to
    open the connection to the device: calling `stop_discovery()` before
    `wait()` leaves the device discoverable but unconnectable, and `wait()` then
    times out after 20 s with no useful error.
    """

    def __init__(self):
        self._browser = None

    def __call__(self, timeout: int = DISCOVERY_TIMEOUT) -> list:
        import pychromecast

        if self._browser is not None:
            self._browser.stop_discovery()
            self._browser = None

        casts, browser = pychromecast.get_chromecasts(timeout=timeout)
        self._browser = browser
        return casts


discover_devices = _Discovery()


class Caster:
    """Plays audio on one cast device, resolved by UUID."""

    def __init__(
        self,
        device_uuid: uuidlib.UUID,
        discover: Callable[..., list] = discover_devices,
        discovery_timeout: int = DISCOVERY_TIMEOUT,
        settle: float = SETTLE_AFTER_QUIT,
        finish_timeout: float = FINISH_TIMEOUT,
    ):
        self.device_uuid = device_uuid
        self.discover = discover
        self.discovery_timeout = discovery_timeout
        self.settle = settle
        self.finish_timeout = finish_timeout
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

    def _take_over(self, device) -> None:
        """Make room for our own playback.

        🔴 Whatever app is running owns the media session. With YouTube open on
        a Chromecast, a LOAD goes to YouTube, which ignores it: the announcement
        is silently lost. Quitting the foreign app hands the device back to the
        default receiver. Our own receiver is left alone — relaunching it would
        cut short audio that is already playing.
        """
        current = getattr(device, "app_id", None)
        if current in (None, MEDIA_RECEIVER_APP_ID):
            return

        log.info("desalojando la app %s del dispositivo para poder hablar", current)
        device.quit_app()
        if self.settle:
            time.sleep(self.settle)

    def _wait_until_playing(self, controller, url: str, timeout: float) -> None:
        """Confirm that *this* clip actually started.

        Reporting success without checking is worse than failing: the person is
        told the house was warned when nothing came out of the speakers.

        🔴 The device has to name our URL. An empty `content_id` means it has
        not told us anything yet, never that our audio is loaded: a freshly
        launched receiver reports BUFFERING with nothing in it, and taking that
        as good is how a service alert was marked as announced while the
        speaker stayed silent. Waiting costs a few polls; guessing costs the
        warning.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            controller.update_status()
            status = controller.status
            if status.idle_reason == "ERROR":
                raise CastError("el dispositivo rechazó el audio")

            if getattr(status, "content_id", None) == url:
                if status.player_state in ("PLAYING", "BUFFERING"):
                    return
                # A clip can be over before the first poll: that still counts.
                if status.idle_reason == "FINISHED":
                    return
            time.sleep(0.2)

        raise CastError("el audio no empezó a sonar (¿el equipo está ocupado o apagado?)")

    def _wait_until_finished(self, controller, url: str, timeout: float) -> None:
        """Wait for the clip to end. Only used when the volume has to go back:
        restoring it mid-sentence would drop the tail of the announcement."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            controller.update_status()
            status = controller.status
            if getattr(status, "content_id", None) != url:
                return  # someone else took the session; not ours to wait for
            if status.player_state not in ("PLAYING", "BUFFERING"):
                return
            time.sleep(0.2)

    @staticmethod
    def _raise_volume(device, min_volume: int | None) -> float | None:
        """Lift the volume to the floor, returning what to put back afterwards.

        None means it was already loud enough and nothing has to be restored.
        """
        if min_volume is None:
            return None
        current = getattr(getattr(device, "status", None), "volume_level", None)
        floor = min_volume / 100
        if current is None or current >= floor:
            return None
        log.info("subo el volumen de %.2f a %.2f para un aviso urgente", current, floor)
        device.set_volume(floor)
        return current

    def _finish_deadline(self, expected_seconds: float | None) -> float:
        if expected_seconds is None:
            return self.finish_timeout
        return min(expected_seconds + FINISH_MARGIN, self.finish_timeout)

    def play(
        self,
        url: str,
        timeout: float = PLAYBACK_TIMEOUT,
        min_volume: int | None = None,
        expected_seconds: float | None = None,
    ) -> None:
        """Play the audio, optionally guaranteeing a minimum volume for it.

        The floor is for urgent announcements: a house left at low volume turns
        a warning into nothing. It is put back afterwards, including when the
        audio fails, so an alert never leaves the speakers loud for good.
        """
        device = self._resolve()
        self._take_over(device)
        previous = self._raise_volume(device, min_volume)

        controller = device.media_controller
        try:
            controller.play_media(url, AUDIO_MIME)
            controller.block_until_active(timeout=self.discovery_timeout)
            self._wait_until_playing(controller, url, timeout)
            if previous is not None:
                self._wait_until_finished(controller, url, self._finish_deadline(expected_seconds))
        finally:
            if previous is not None:
                device.set_volume(previous)

    def set_volume(self, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise CastError("El volumen tiene que estar entre 0 y 100")
        self._resolve().set_volume(percent / 100)

    def stop(self) -> None:
        self._resolve().media_controller.stop()

    def turn_off(self) -> None:
        """Close whatever app is running and leave the device idle.

        There is no power-off in the cast protocol. This is as far as it goes:
        the device stops showing anything, and a TV set to sleep on loss of
        signal follows on its own through HDMI-CEC.
        """
        device = self._resolve()
        if getattr(device, "app_id", None) is None:
            return
        device.quit_app()

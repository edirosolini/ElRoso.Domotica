"""Lo que el CT le diría a una tele por Cast, mandado a su app; sin confirmación, por Cast."""

from __future__ import annotations

import logging

from homeauto.tele import TeleLink
from homeauto.voice.caster import FINISH_MARGIN, FINISH_TIMEOUT

log = logging.getLogger(__name__)

# Cuánto se espera a que la app diga que recibió una orden.
ACK_TIMEOUT = 10


class TeleCaster:
    """Envuelve al Caster de una tele: audio y pantalla van a la app si está viva."""

    def __init__(
        self,
        alias: str,
        caster,
        link: TeleLink,
        ack_timeout: float = ACK_TIMEOUT,
        finish_timeout: float = FINISH_TIMEOUT,
    ):
        self.alias = alias
        self.caster = caster
        self.link = link
        self.ack_timeout = ack_timeout
        self.finish_timeout = finish_timeout
        # Si lo último que sonó salió por Cast.
        self._by_cast = False

    def __getattr__(self, name):
        return getattr(self.caster, name)

    def play(
        self, url: str, min_volume: int | None = None, expected_seconds: float | None = None
    ) -> None:
        """Lo hace sonar la app y espera a que termine; si no confirma, lo dice por Cast."""
        if self.link.can(self.alias, "play"):
            seq = self.link.send(
                self.alias, "play", url=url, min_volume=min_volume, seconds=expected_seconds
            )
            state = self.link.wait(self.alias, seq, ("received",), self.ack_timeout)
            if state == "received":
                state = self.link.wait(
                    self.alias, seq, ("done",), self._finish_deadline(expected_seconds)
                )
            if state in ("done", "cancelled"):
                self._by_cast = False
                return
            self.link.cancel(self.alias, seq)
            log.warning("la app de %s no confirmó el audio (%s): va por Cast", self.alias, state)
        self._by_cast = True
        self.caster.play(url, min_volume=min_volume, expected_seconds=expected_seconds)

    def show(self, url: str) -> None:
        """Muestra la página en la app; si no confirma, por DashCast."""
        if self.link.can(self.alias, "show"):
            seq = self.link.send(self.alias, "show", url=url)
            state = self.link.wait(self.alias, seq, ("received",), self.ack_timeout)
            if state in ("received", "done", "cancelled"):
                return
            self.link.cancel(self.alias, seq)
            log.warning("la app de %s no confirmó la página (%s): va por Cast", self.alias, state)
        self.caster.show(url)

    def stop(self) -> None:
        """Corta el audio en la app si está viva, y por Cast si no o si lo último salió por ahí."""
        app = self.link.can(self.alias, "play")
        if app:
            self.link.send(self.alias, "stop")
        if not app or self._by_cast:
            self.caster.stop()

    def set_volume(self, percent: int) -> None:
        self.caster.set_volume(percent)

    def turn_off(self) -> None:
        self.caster.turn_off()

    def _finish_deadline(self, expected_seconds: float | None) -> float:
        if expected_seconds is None:
            return self.finish_timeout
        return min(expected_seconds + FINISH_MARGIN, self.finish_timeout)

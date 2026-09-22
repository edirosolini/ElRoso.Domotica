"""Control de un equipo Google cast, resuelto por UUID y nunca por IP."""

from __future__ import annotations

import logging
import time
import uuid as uuidlib
from typing import Callable

log = logging.getLogger(__name__)

DISCOVERY_TIMEOUT = 20
AUDIO_MIME = "audio/wav"

# El receptor por defecto de Google: la app donde corre nuestro audio.
MEDIA_RECEIVER_APP_ID = "CC1AD845"

PLAYBACK_TIMEOUT = 20
# Tope para esperar un clip cuya duración no se pudo leer.
FINISH_TIMEOUT = 120
# Margen sobre la duración: el equipo arranca un instante después de pedirlo.
FINISH_MARGIN = 5
SETTLE_AFTER_QUIT = 2


class CastError(Exception):
    """No se pudo llegar al equipo, o se le pidió algo inválido."""


class _Discovery:
    """Descubrimiento mDNS real. Se importa tarde para que los tests no toquen la red.

    El browser de zeroconf se deja vivo: pychromecast lo necesita para abrir la
    conexión, y pararlo antes de `wait()` deja el equipo inalcanzable.
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
    """Reproduce audio en un equipo cast, resuelto por UUID."""

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
        """Olvida el equipo cacheado para que la próxima llamada lo redescubra."""
        self._device = None

    def _perform(self, action: Callable[[object], object]):
        """Hace algo en el equipo, buscándolo de nuevo si se movió.

        El objeto resuelto se queda con la IP que el equipo tenía al encontrarlo,
        y son DHCP. Redescubrir cuesta veinte segundos de mDNS, así que solo pasa
        después de un fallo. Un reintento puede repetir un anuncio que sí sonó.
        """
        try:
            return action(self._resolve())
        except CastError:
            raise
        except Exception as exc:  # noqa: BLE001 - cualquier fallo de conexión
            log.warning("%s no contestó (%s): lo busco de nuevo", self.device_uuid, exc)
            self.forget()

        try:
            return action(self._resolve())
        except CastError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CastError(f"no pude hablarle al equipo: {exc}") from exc

    def device_name(self) -> str:
        return self._perform(lambda device: device.cast_info.friendly_name)

    def _take_over(self, device) -> None:
        """Hace lugar para nuestro propio audio.

        La app que está corriendo es dueña de la sesión de medios, así que se
        desaloja la ajena. El receptor propio se respeta: relanzarlo cortaría el
        audio en curso.
        """
        current = getattr(device, "app_id", None)
        if current in (None, MEDIA_RECEIVER_APP_ID):
            return

        log.info("desalojando la app %s del dispositivo para poder hablar", current)
        device.quit_app()
        if self.settle:
            time.sleep(self.settle)

    def _wait_until_playing(self, controller, url: str, timeout: float) -> None:
        """Confirma que empezó a sonar *este* clip.

        El equipo tiene que nombrar nuestra URL: un `content_id` vacío significa
        que todavía no dijo nada, nunca que nuestro audio esté cargado.
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
                # Un clip puede terminar antes del primer sondeo: igual cuenta.
                if status.idle_reason == "FINISHED":
                    return
            time.sleep(0.2)

        raise CastError("el audio no empezó a sonar (¿el equipo está ocupado o apagado?)")

    def _wait_until_finished(self, controller, url: str, timeout: float) -> None:
        """Espera a que el clip termine. Solo se usa cuando hay que devolver el
        volumen: restaurarlo a mitad de frase se comería el final del anuncio."""
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
        """Sube el volumen al piso y devuelve qué hay que restaurar después.

        None significa que ya estaba suficientemente alto y no hay que tocar nada.
        """
        if min_volume is None:
            return None
        current = getattr(getattr(device, "status", None), "volume_level", None)
        floor = min_volume / 100
        if current is None or current >= floor:
            return None
        # El piso vale para todo lo que se dice, no solo para lo urgente: decir
        # "urgente" acá mandaba a buscar una urgencia que no existía.
        log.info("subo el volumen de %.2f a %.2f, estaba por debajo del piso", current, floor)
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
        """Reproduce el audio, garantizando un volumen mínimo si se pide.

        El piso existe porque una casa que quedó en volumen bajo convierte un
        aviso en nada. Se restaura al final, también si el audio falla.
        """
        self._perform(
            lambda device: self._play_on(device, url, timeout, min_volume, expected_seconds)
        )

    def _play_on(
        self,
        device,
        url: str,
        timeout: float,
        min_volume: int | None,
        expected_seconds: float | None,
    ) -> None:
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
        self._perform(lambda device: device.set_volume(percent / 100))

    def stop(self) -> None:
        self._perform(lambda device: device.media_controller.stop())

    def turn_off(self) -> None:
        """Cierra la app que esté corriendo y deja el equipo en reposo.

        No existe apagar por Cast. Esto es lo máximo: el equipo deja de mostrar
        nada, y un televisor configurado para dormirse al perder señal se apaga
        solo por HDMI-CEC.
        """
        def close(device) -> None:
            if getattr(device, "app_id", None) is None:
                return
            device.quit_app()

        self._perform(close)

"""Control de un equipo Google cast, resuelto por UUID y nunca por IP."""

from __future__ import annotations

import logging
import threading
import time
import uuid as uuidlib
from typing import Callable

log = logging.getLogger(__name__)

DISCOVERY_TIMEOUT = 20
DISCOVERY_POLL = 0.2
AUDIO_MIME = "audio/wav"

# El receptor por defecto de Google: la app donde corre nuestro audio.
MEDIA_RECEIVER_APP_ID = "CC1AD845"
# DashCast: muestra una página web en un equipo con pantalla.
APP_DASHCAST = "84912283"

PLAYBACK_TIMEOUT = 20
# Tope para esperar un clip cuya duración no se pudo leer.
FINISH_TIMEOUT = 120
# Margen sobre la duración: el equipo arranca un instante después de pedirlo.
FINISH_MARGIN = 5
SETTLE_AFTER_QUIT = 2


class CastError(Exception):
    """No se pudo llegar al equipo, o se le pidió algo inválido."""


def _start_browser():
    """Arranca el zeroconf y el browser mDNS reales, con import tardío."""
    import pychromecast
    import zeroconf

    browser = pychromecast.CastBrowser(pychromecast.SimpleCastListener(), zeroconf.Zeroconf())
    browser.start_discovery()
    return browser


def _build_chromecast(cast_info, zconf, timeout=None):
    """Arma el Chromecast de un equipo visto por el browser, con el zeroconf compartido."""
    import pychromecast

    return pychromecast.get_chromecast_from_cast_info(cast_info, zconf, timeout=timeout)


class _Discovery:
    """Un solo zeroconf y un solo browser mDNS para todo el proceso, que nunca se paran."""

    def __init__(self, start=_start_browser, build=_build_chromecast, sleep=time.sleep):
        self._start = start
        self._build = build
        self._sleep = sleep
        self._browser = None
        self._lock = threading.Lock()

    def _running(self):
        with self._lock:
            if self._browser is None:
                self._browser = self._start()
            return self._browser

    def find(self, device_uuid: uuidlib.UUID, timeout: float = DISCOVERY_TIMEOUT) -> list:
        """Espera hasta `timeout` a que mDNS vea el UUID y devuelve una lista con su equipo, o levanta CastError."""
        browser = self._running()
        deadline = time.monotonic() + timeout
        while True:
            info = browser.devices.get(device_uuid)
            if info is not None:
                return [self._build(info, browser.zc, timeout=timeout or None)]
            if time.monotonic() >= deadline:
                break
            self._sleep(DISCOVERY_POLL)

        names = [getattr(i, "friendly_name", "?") for i in list(browser.devices.values())]
        seen = ", ".join(names) or "ninguno"
        raise CastError(f"No encontré el dispositivo {device_uuid}. Vi: {seen}")

    def host_of(self, device_uuid: uuidlib.UUID) -> str | None:
        """Devuelve la IP que mDNS anuncia hoy para el UUID, o None si no la sabe."""
        if self._browser is None:
            return None
        info = self._browser.devices.get(device_uuid)
        return None if info is None else info.host


discover_devices = _Discovery()


def _dashcast_controller():
    """El controlador de DashCast de pychromecast; se importa tarde como el descubrimiento."""
    from pychromecast.controllers.dashcast import DashCastController

    return DashCastController()


class Caster:
    """Reproduce audio en un equipo cast, resuelto por UUID."""

    def __init__(
        self,
        device_uuid: uuidlib.UUID,
        discover: Callable[..., list] | None = None,
        discovery_timeout: int = DISCOVERY_TIMEOUT,
        settle: float = SETTLE_AFTER_QUIT,
        finish_timeout: float = FINISH_TIMEOUT,
        locate: Callable[[uuidlib.UUID], str | None] | None = None,
        dashcast: Callable[[], object] = _dashcast_controller,
        screen: Callable[[], str | None] | None = None,
        discovery: _Discovery = discover_devices,
    ):
        self.device_uuid = device_uuid
        self.dashcast = dashcast
        # La página a volver a mostrar después de un anuncio, o None para dejarla cerrada.
        self.screen = screen
        if discover is None:
            def discover(timeout=DISCOVERY_TIMEOUT):
                return discovery.find(device_uuid, timeout)
        self.discover = discover
        self.locate = locate if locate is not None else discovery.host_of
        self.discovery_timeout = discovery_timeout
        self.settle = settle
        self.finish_timeout = finish_timeout
        self._device = None

    def _resolve(self):
        if self._device is not None:
            if not self._moved(self._device):
                return self._device
            self.forget()

        found = self.discover(timeout=self.discovery_timeout)
        for candidate in found:
            if candidate.cast_info.uuid == self.device_uuid:
                candidate.wait(timeout=self.discovery_timeout)
                self._device = candidate
                return candidate

        seen = ", ".join(getattr(c.cast_info, "friendly_name", "?") for c in found) or "ninguno"
        raise CastError(f"No encontré el dispositivo {self.device_uuid}. Vi: {seen}")

    def _moved(self, device) -> bool:
        """Dice si el equipo cacheado está conectado a otra IP que la que anuncia mDNS."""
        try:
            announced = self.locate(self.device_uuid)
        except Exception as exc:  # noqa: BLE001
            log.debug("no pude ubicar %s: %s", self.device_uuid, exc)
            return False
        if announced is None:
            return False

        client = getattr(device, "socket_client", None)
        connected = client.host if client is not None else device.cast_info.host
        if connected == announced:
            return False

        log.warning(
            "%s está conectado a %s pero anuncia %s: lo busco de nuevo",
            self.device_uuid,
            connected,
            announced,
        )
        return True

    def forget(self) -> None:
        """Olvida el equipo cacheado para que la próxima llamada lo redescubra."""
        device, self._device = self._device, None
        if device is None:
            return
        try:
            # timeout=0 no espera a que termine el hilo del socket.
            device.disconnect(timeout=0)
        except Exception as exc:  # noqa: BLE001
            log.debug("no pude desconectar %s: %s", self.device_uuid, exc)

    def _perform(self, action: Callable[[object], object]):
        """Hace algo en el equipo, buscándolo de nuevo si se movió.

        El objeto resuelto se queda con la IP que el equipo tenía al encontrarlo,
        y son DHCP. Redescubrir puede tardar hasta veinte segundos de mDNS, así que solo pasa
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
        was_screen = getattr(device, "app_id", None) == APP_DASHCAST
        self._take_over(device)
        previous = self._raise_volume(device, min_volume)

        controller = device.media_controller
        try:
            controller.play_media(url, AUDIO_MIME)
            controller.block_until_active(timeout=self.discovery_timeout)
            self._wait_until_playing(controller, url, timeout)
            if previous is not None or was_screen:
                self._wait_until_finished(controller, url, self._finish_deadline(expected_seconds))
        finally:
            if previous is not None:
                device.set_volume(previous)
        if was_screen:
            self._restore(device)

    def _show_on(self, device, url: str) -> None:
        # Sin force, DashCast la abre en un iframe y la CSP de la página lo bloquea.
        controller = self.dashcast()
        device.register_handler(controller)
        controller.load_url(url, force=True)

    def _restore(self, device) -> None:
        """Vuelve a mostrar la página que corresponda; una falla no tumba el anuncio."""
        if self.screen is None:
            return
        try:
            page = self.screen()
            if page:
                self._show_on(device, page)
        except Exception as exc:  # noqa: BLE001
            log.warning("no pude volver a mostrar la pantalla en %s: %s", self.device_uuid, exc)

    def show(self, url: str) -> None:
        """Muestra la página en el equipo con DashCast."""
        self._perform(lambda device: self._show_on(device, url))

    def showing(self) -> bool:
        """Si el equipo tiene DashCast abierto."""
        return self._perform(lambda device: getattr(device, "app_id", None) == APP_DASHCAST)

    def hide(self) -> bool:
        """Cierra DashCast si sigue abierto; False si no estaba o había otra app."""
        def close(device) -> bool:
            if getattr(device, "app_id", None) != APP_DASHCAST:
                return False
            device.quit_app()
            return True

        return self._perform(close)

    def set_volume(self, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise CastError("El volumen tiene que estar entre 0 y 100")
        self._perform(lambda device: device.set_volume(percent / 100))

    def stop(self) -> None:
        """Corta el audio en curso; sin audio sonando no hace nada."""
        def halt(device) -> None:
            controller = device.media_controller
            state = getattr(getattr(controller, "status", None), "player_state", None)
            if state in ("PLAYING", "BUFFERING", "PAUSED"):
                controller.stop()

        self._perform(halt)

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

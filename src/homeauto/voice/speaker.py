"""El parlante como una sola cosa: decir una frase en voz alta.

Junta la síntesis, publicar el audio por HTTP y avisarle al equipo que lo baje.
Todo lo que está por encima solo dice qué quiere que se diga.
"""

from __future__ import annotations

from pathlib import Path

from homeauto.voice.tts import duration_seconds

# Piso de volumen para todo lo hablado. Después se le devuelve el suyo al equipo.
MIN_VOLUME = 60
ALARM_MIN_VOLUME = 90


class Speaker:
    def __init__(self, synth, caster, media_server, min_volume: int | None = MIN_VOLUME):
        self.synth = synth
        self.caster = caster
        self.media_server = media_server
        self.min_volume = min_volume
        self._serving = False

    def _ensure_serving(self) -> None:
        if not self._serving:
            self.media_server.start()
            self._serving = True

    def say(self, text: str, chime: bool | str = False, min_volume: int | None = None) -> Path:
        """Sintetiza, publica y reproduce. Devuelve el archivo de audio usado.

        El piso de volumen se aplica acá, para todos los llamadores; `min_volume`
        lo reemplaza para esta frase. `chime` pega adelante un sonido, en el mismo
        clip y el mismo cast.
        """
        path = self.synth.say(text, chime=chime)
        self._ensure_serving()
        self.caster.play(
            self.media_server.url_for(path.name),
            min_volume=self.min_volume if min_volume is None else min_volume,
            expected_seconds=duration_seconds(path),
        )
        return path

    def set_volume(self, percent: int) -> None:
        self.caster.set_volume(percent)

    def stop(self) -> None:
        self.caster.stop()

    def turn_off(self) -> None:
        self.caster.turn_off()

    def show(self, url: str) -> None:
        self.caster.show(url)

    def showing(self) -> bool:
        return self.caster.showing()

    def hide(self) -> bool:
        return self.caster.hide()

    def device_name(self) -> str:
        return self.caster.device_name()

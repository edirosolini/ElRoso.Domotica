"""The speaker as a single thing: say a phrase out loud.

Ties together synthesis, publishing the audio over HTTP, and telling the device
to fetch it. Everything above this layer only says what it wants said.
"""

from __future__ import annotations

from pathlib import Path

from homeauto.voice.tts import duration_seconds

# Everything the house says goes out at least this loud, and the device gets
# its own level back afterwards. A house left at low volume turns an
# announcement into nothing, and nobody remembers to check the volume before
# an alarm goes off.
MIN_VOLUME = 60


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

    def say(self, text: str) -> Path:
        """Synthesize, publish and play. Returns the audio file used.

        The floor is applied here, and not by whoever asks for the phrase,
        because there are five different callers and every one of them wants
        the same thing: to be heard.
        """
        path = self.synth.say(text)
        self._ensure_serving()
        self.caster.play(
            self.media_server.url_for(path.name),
            min_volume=self.min_volume,
            expected_seconds=duration_seconds(path),
        )
        return path

    def set_volume(self, percent: int) -> None:
        self.caster.set_volume(percent)

    def stop(self) -> None:
        self.caster.stop()

    def turn_off(self) -> None:
        self.caster.turn_off()

    def device_name(self) -> str:
        return self.caster.device_name()

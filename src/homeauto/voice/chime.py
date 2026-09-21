"""The beeps in front of an alarm, built to match the wav they go into."""

from __future__ import annotations

import array
import logging
import math
import wave
from pathlib import Path

log = logging.getLogger(__name__)

# (hertz, seconds). Zero is silence: the gap between beeps.
BEEPS = (
    (880, 0.18),
    (0, 0.12),
    (880, 0.18),
    (0, 0.12),
    (1320, 0.26),
    (0, 0.40),
)
SECONDS = sum(length for _, length in BEEPS)

AMPLITUDE = 0.35
# A tone that starts at full amplitude clicks.
FADE_SECONDS = 0.006
SUPPORTED_WIDTH = 2


def frames(rate: int, width: int, channels: int, beeps=BEEPS) -> bytes:
    """The chime as raw frames in the format asked for."""
    if width != SUPPORTED_WIDTH:
        raise ValueError(f"solo se soportan muestras de {SUPPORTED_WIDTH} bytes")

    peak = int(AMPLITUDE * 32767)
    fade = max(1, int(FADE_SECONDS * rate))
    samples = array.array("h")

    for hertz, length in beeps:
        total = int(length * rate)
        for index in range(total):
            if hertz == 0:
                value = 0
            else:
                envelope = min(1.0, index / fade, (total - index) / fade)
                value = int(peak * envelope * math.sin(2 * math.pi * hertz * index / rate))
            samples.extend([value] * channels)

    return samples.tobytes()


def prepend(path: Path) -> None:
    """Puts the chime in front of a wav, in place. A clip it cannot read is left alone."""
    try:
        with wave.open(str(path), "rb") as source:
            params = source.getparams()
            voice = source.readframes(source.getnframes())
        beeps = frames(params.framerate, params.sampwidth, params.nchannels)
    except Exception as exc:  # noqa: BLE001 - un chime no puede costar el aviso
        log.warning("no pude ponerle el sonido a %s: %s", path, exc)
        return

    with wave.open(str(path), "wb") as target:
        target.setnchannels(params.nchannels)
        target.setsampwidth(params.sampwidth)
        target.setframerate(params.framerate)
        target.writeframes(beeps + voice)

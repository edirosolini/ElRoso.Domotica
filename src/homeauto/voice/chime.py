"""Los beeps que van delante de un aviso, con el formato del wav que los recibe."""

from __future__ import annotations

import array
import logging
import math
import wave
from pathlib import Path

log = logging.getLogger(__name__)

AMPLITUDE = 0.35
# Tope de amplitud de cualquier tono; `frames()` recorta lo que lo pase.
MAX_AMPLITUDE = 0.9

# (hertz, segundos, amplitud). Cero hertz es silencio: el hueco entre beeps.
BEEPS = (
    (880, 0.18, AMPLITUDE),
    (0, 0.12, 0),
    (880, 0.18, AMPLITUDE),
    (0, 0.12, 0),
    (1320, 0.26, AMPLITUDE),
    (0, 0.40, 0),
)
SECONDS = sum(length for _, length, _ in BEEPS)

# Un solo tono corto: llama la atención sin sonar a despertador.
SOFT_BEEPS = (
    (660, 0.22, AMPLITUDE),
    (0, 0.40, 0),
)


def _wake(bursts: int, low: float, high: float) -> tuple[tuple[int, float, float], ...]:
    """Ráfagas de dos tonos con la amplitud subiendo de `low` a `high`."""
    beeps = []
    for index in range(bursts):
        amplitude = round(low + (high - low) * index / (bursts - 1), 3)
        beeps += [
            (1000, 0.14, amplitude),
            (0, 0.06, 0),
            (1500, 0.20, amplitude),
            (0, 0.22, 0),
        ]
    beeps.append((0, 0.30, 0))
    return tuple(beeps)


ALARM = "alarm"
SOFT = "soft"
# Los niveles del despertador, de menor a mayor.
WAKE_LEVELS = ("wake1", "wake2", "wake3")
WAKE = WAKE_LEVELS[0]
WAKE_BEEPS = (
    _wake(4, 0.45, 0.80),
    _wake(6, 0.55, 0.88),
    _wake(8, 0.65, MAX_AMPLITUDE),
)
SOUNDS = {ALARM: BEEPS, SOFT: SOFT_BEEPS, **dict(zip(WAKE_LEVELS, WAKE_BEEPS))}

# Un tono que arranca a amplitud plena hace click.
FADE_SECONDS = 0.006
SUPPORTED_WIDTH = 2


def sound(chime: bool | str) -> str | None:
    """El nombre del sonido pedido: `True` es el de alarma, `False` ninguno."""
    if chime is True:
        return ALARM
    if not chime:
        return None
    if chime not in SOUNDS:
        raise ValueError(f"sonido desconocido: {chime}")
    return chime


def frames(rate: int, width: int, channels: int, beeps=BEEPS) -> bytes:
    """El chime como frames crudos, en el formato pedido."""
    if width != SUPPORTED_WIDTH:
        raise ValueError(f"solo se soportan muestras de {SUPPORTED_WIDTH} bytes")

    fade = max(1, int(FADE_SECONDS * rate))
    samples = array.array("h")

    for hertz, length, amplitude in beeps:
        total = int(length * rate)
        peak = int(min(amplitude, MAX_AMPLITUDE) * 32767)
        for index in range(total):
            if hertz == 0:
                value = 0
            else:
                envelope = min(1.0, index / fade, (total - index) / fade)
                value = int(peak * envelope * math.sin(2 * math.pi * hertz * index / rate))
            samples.extend([value] * channels)

    return samples.tobytes()


def prepend(path: Path, name: str = ALARM) -> None:
    """Pega el chime delante de un wav, en el lugar. Un clip ilegible se deja como está."""
    try:
        with wave.open(str(path), "rb") as source:
            params = source.getparams()
            voice = source.readframes(source.getnframes())
        beeps = frames(params.framerate, params.sampwidth, params.nchannels, SOUNDS[name])
    except Exception as exc:  # noqa: BLE001 - un chime no puede costar el aviso
        log.warning("no pude ponerle el sonido a %s: %s", path, exc)
        return

    with wave.open(str(path), "wb") as target:
        target.setnchannels(params.nchannels)
        target.setsampwidth(params.sampwidth)
        target.setframerate(params.framerate)
        target.writeframes(beeps + voice)

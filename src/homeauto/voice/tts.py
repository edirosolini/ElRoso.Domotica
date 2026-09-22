"""Síntesis de voz con Piper, con cache en disco.

La síntesis es determinística para un texto y una voz, así que el resultado se
cachea: repetir un anuncio no cuesta nada después de la primera vez.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
import subprocess
import wave
from pathlib import Path
from typing import Callable, Protocol

from homeauto.voice import chime as chime_audio

log = logging.getLogger(__name__)

# Un Chromecast nunca reporta PLAYING para un clip más corto que esto, así que
# se los padea con silencio.
DEFAULT_MIN_SECONDS = 1.5

# Ritmo de habla y pausa entre oraciones. Los dos son parte de la clave del
# cache: cambiarlos deja huérfano lo sintetizado con el ritmo viejo.
DEFAULT_LENGTH_SCALE = 1.40
DEFAULT_SENTENCE_SILENCE = 1.10


class TtsError(Exception):
    """La síntesis falló, o se le pidió algo que no puede decir."""


class Runner(Protocol):
    """Convierte texto en un wav en la ruta indicada."""

    def __call__(self, text: str, out_path: Path) -> None: ...


class PiperRunner:
    """Llama al CLI de piper en un subproceso, con el ritmo al que tiene que hablar."""

    def __init__(
        self,
        python_bin: Path | str,
        voice_path: Path | str,
        length_scale: float | None = DEFAULT_LENGTH_SCALE,
        sentence_silence: float | None = DEFAULT_SENTENCE_SILENCE,
        noise_scale: float | None = None,
        noise_w: float | None = None,
        run: Callable = subprocess.run,
    ):
        self.python_bin = str(python_bin)
        self.voice_path = str(voice_path)
        self.length_scale = length_scale
        self.sentence_silence = sentence_silence
        self.noise_scale = noise_scale
        self.noise_w = noise_w
        self.run = run

    @property
    def pacing(self) -> str:
        """Cómo habla este runner, como string. Va en la clave del cache."""
        return "|".join(
            "" if value is None else f"{value}"
            for value in (self.length_scale, self.sentence_silence,
                          self.noise_scale, self.noise_w)
        )

    def _flags(self) -> list[str]:
        """Solo lo que se configuró: el resto lo sigue decidiendo el modelo de voz."""
        flags: list[str] = []
        for name, value in (
            ("--length-scale", self.length_scale),
            ("--sentence-silence", self.sentence_silence),
            ("--noise-scale", self.noise_scale),
            ("--noise-w-scale", self.noise_w),
        ):
            if value is not None:
                flags += [name, f"{value}"]
        return flags

    def __call__(self, text: str, out_path: Path) -> None:
        # onnxruntime no puede fijar afinidad de hilos dentro de un LXC sin
        # privilegios y loguea un error; fijar la cantidad deja el log limpio.
        env = {**os.environ, "OMP_NUM_THREADS": "1"}
        result = self.run(
            [self.python_bin, "-m", "piper", "-m", self.voice_path, "-f", str(out_path)]
            + self._flags(),
            input=text,
            text=True,
            capture_output=True,
            env=env,
        )
        if result.returncode != 0:
            raise TtsError(f"piper falló ({result.returncode}): {result.stderr.strip()[:300]}")


def duration_seconds(path: Path) -> float | None:
    """Cuánto dura el clip, o None si el archivo no se puede leer."""
    try:
        with wave.open(str(path), "rb") as source:
            rate = source.getframerate()
            return source.getnframes() / rate if rate else None
    except Exception:  # noqa: BLE001 - un wav ilegible no puede romper el anuncio
        log.warning("no pude leer la duración de %s", path)
        return None


def _pad_to_minimum(path: Path, min_seconds: float) -> None:
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        frames = source.readframes(source.getnframes())

    played = len(frames) / (rate * width * channels)
    if played >= min_seconds:
        return

    # Se redondea para arriba: truncar deja el clip un frame por debajo del mínimo.
    missing = math.ceil((min_seconds - played) * rate)
    silence = b"\x00" * (missing * width * channels)

    with wave.open(str(path), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(width)
        target.setframerate(rate)
        target.writeframes(frames + silence)


class VoiceSynth:
    """Produce un wav reproducible para una frase, reusando lo ya hecho."""

    def __init__(
        self,
        cache_dir: Path | str,
        runner: Runner | Callable[[str, Path], None],
        min_seconds: float = DEFAULT_MIN_SECONDS,
        voice: str = "",
        pacing: str = "",
    ):
        self.cache_dir = Path(cache_dir)
        self.runner = runner
        self.min_seconds = min_seconds
        # El ritmo y la voz cambian el audio, así que van en la clave del cache.
        self.pacing = pacing
        self.voice = voice
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Varios equipos piden la misma frase desde varios hilos a la vez.
        self._lock = threading.Lock()

    def say(self, text: str, chime: bool = False) -> Path:
        """`chime` pega adelante los beeps de alarma. Va en la clave del cache."""
        text = text.strip()
        if not text:
            raise TtsError("El texto está vacío")

        cached = self.cache_dir / f"{self._key(text, chime)}.wav"
        if cached.is_file():
            return cached

        with self._lock:
            # Otro pudo haberla sintetizado mientras esperábamos el candado.
            if cached.is_file():
                return cached

            # Se arma aparte y se mueve al lugar: una corrida fallida no puede
            # envenenar el cache, y el id de hilo evita que dos choquen.
            pending = cached.with_suffix(f".{threading.get_ident():x}.partial")
            try:
                self.runner(text, pending)
                if chime:
                    chime_audio.prepend(pending)
                _pad_to_minimum(pending, self.min_seconds)
                pending.replace(cached)
            finally:
                pending.unlink(missing_ok=True)
        return cached

    def _key(self, text: str, chime: bool = False) -> str:
        seed = f"{self.voice}\x00{self.pacing}\x00{'chime' if chime else ''}\x00{text}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

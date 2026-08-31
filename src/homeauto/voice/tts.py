"""Text to speech through Piper, with an on-disk cache.

Synthesis is deterministic for a given text and voice, so the result is cached:
repeating an announcement costs nothing after the first time.
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

log = logging.getLogger(__name__)

# A clip shorter than this never reaches the PLAYING state on a Chromecast
# device: it finishes before the receiver reports back. Padding with silence
# is what makes playback observable, and audible.
DEFAULT_MIN_SECONDS = 1.5


class TtsError(Exception):
    """Synthesis failed or was asked for something it cannot say."""


class Runner(Protocol):
    """Turns text into a wav file at the given path."""

    def __call__(self, text: str, out_path: Path) -> None: ...


class PiperRunner:
    """Calls the piper CLI in a subprocess."""

    def __init__(self, python_bin: Path | str, voice_path: Path | str):
        self.python_bin = str(python_bin)
        self.voice_path = str(voice_path)

    def __call__(self, text: str, out_path: Path) -> None:
        # onnxruntime cannot set thread affinity inside an unprivileged LXC and
        # logs an error for it; pinning the thread count keeps the log clean.
        env = {**os.environ, "OMP_NUM_THREADS": "1"}
        result = subprocess.run(
            [self.python_bin, "-m", "piper", "-m", self.voice_path, "-f", str(out_path)],
            input=text,
            text=True,
            capture_output=True,
            env=env,
        )
        if result.returncode != 0:
            raise TtsError(f"piper falló ({result.returncode}): {result.stderr.strip()[:300]}")


def duration_seconds(path: Path) -> float | None:
    """How long the clip lasts, or None if the file cannot be read.

    Whoever waits for the audio to end needs a real bound: a fixed timeout is
    either too short for the morning briefing or too long for one sentence.
    """
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

    # Round up: truncating leaves the clip one frame short of the minimum.
    missing = math.ceil((min_seconds - played) * rate)
    silence = b"\x00" * (missing * width * channels)

    with wave.open(str(path), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(width)
        target.setframerate(rate)
        target.writeframes(frames + silence)


class VoiceSynth:
    """Produces a playable wav for a phrase, reusing previous work."""

    def __init__(
        self,
        cache_dir: Path | str,
        runner: Runner | Callable[[str, Path], None],
        min_seconds: float = DEFAULT_MIN_SECONDS,
        voice: str = "",
    ):
        self.cache_dir = Path(cache_dir)
        self.runner = runner
        self.min_seconds = min_seconds
        # 🔴 The voice belongs in the cache key. Keyed on the text alone, every
        # phrase already said kept playing in the previous voice after a voice
        # change, with nothing in the logs to show why.
        self.voice = voice
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # An announcement to several devices asks for the same phrase from
        # several threads at once. Without this they raced on the same partial
        # file: the first to finish renamed it and the rest blew up.
        self._lock = threading.Lock()

    def say(self, text: str) -> Path:
        text = text.strip()
        if not text:
            raise TtsError("El texto está vacío")

        cached = self.cache_dir / f"{self._key(text)}.wav"
        if cached.is_file():
            return cached

        with self._lock:
            # Someone else may have synthesized it while we waited for the lock.
            if cached.is_file():
                return cached

            # Build aside and move into place, so a failed run never poisons the
            # cache. The name carries the thread id so two runs never collide.
            pending = cached.with_suffix(f".{threading.get_ident():x}.partial")
            try:
                self.runner(text, pending)
                _pad_to_minimum(pending, self.min_seconds)
                pending.replace(cached)
            finally:
                pending.unlink(missing_ok=True)
        return cached

    def _key(self, text: str) -> str:
        seed = f"{self.voice}\x00{text}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

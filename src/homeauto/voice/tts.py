"""Text to speech through Piper, with an on-disk cache.

Synthesis is deterministic for a given text and voice, so the result is cached:
repeating an announcement costs nothing after the first time.
"""

from __future__ import annotations

import hashlib
import math
import os
import subprocess
import wave
from pathlib import Path
from typing import Callable, Protocol

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
    ):
        self.cache_dir = Path(cache_dir)
        self.runner = runner
        self.min_seconds = min_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def say(self, text: str) -> Path:
        text = text.strip()
        if not text:
            raise TtsError("El texto está vacío")

        cached = self.cache_dir / f"{self._key(text)}.wav"
        if cached.is_file():
            return cached

        # Build aside and move into place, so a failed run never poisons the cache.
        pending = cached.with_suffix(".partial")
        try:
            self.runner(text, pending)
            _pad_to_minimum(pending, self.min_seconds)
            pending.replace(cached)
        finally:
            pending.unlink(missing_ok=True)
        return cached

    def _key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

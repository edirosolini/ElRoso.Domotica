"""La respuesta de la casa como nota de voz: Telegram solo acepta OGG/Opus."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

ENCODER = "opusenc"
BITRATE = "24"


class VoicemailError(Exception):
    """La respuesta no se pudo convertir en nota de voz."""


class OpusEncoder:
    def __init__(self, binary: str = ENCODER, run: Callable[..., object] = subprocess.run):
        self.binary = binary
        self.run = run

    def __call__(self, wav: Path, ogg: Path) -> None:
        try:
            result = self.run(
                [self.binary, "--quiet", "--bitrate", BITRATE, str(wav), str(ogg)],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise VoicemailError(f"no pude ejecutar {self.binary}: {exc}") from exc

        if result.returncode != 0:
            raise VoicemailError(f"{self.binary} falló ({result.returncode}): {result.stderr}")


class Voicemail:
    """Convierte una frase en nota de voz, reusando lo ya codificado."""

    def __init__(self, synth, encode: Callable[[Path, Path], None] | None = None):
        self.synth = synth
        self.encode = encode or OpusEncoder()

    def __call__(self, text: str) -> Path:
        wav = self.synth.say(text)
        ogg = wav.with_suffix(".ogg")
        if ogg.is_file():
            return ogg

        pending = ogg.with_suffix(".partial.ogg")
        try:
            self.encode(wav, pending)
            pending.replace(ogg)
        finally:
            pending.unlink(missing_ok=True)
        return ogg

"""Pedir que algo salga por el parlante, dicho al final del mensaje."""

from __future__ import annotations

import re

# Anclado al final: "el parlante del comedor anda mal" no es un pedido.
_ALOUD = re.compile(
    r"[,\s]*(?:y\s+)?(?:deci[rl]o|reproduc[ií]\w*|pas[aá]\w*|hac[eé]\w*\s+sonar)?\s*"
    r"(?:(?:por|en)\s+(?:el|los)\s+(?:parlante|parlantes|altavoz|altavoces)|en\s+voz\s+alta)"
    r"\s*[.!]*$",
    re.IGNORECASE,
)


def strip_aloud(text: str) -> tuple[bool, str]:
    """True si el mensaje pide el parlante, más el mensaje sin esa coletilla."""
    match = _ALOUD.search(text)
    if not match:
        return False, text
    return True, text[: match.start()].strip()

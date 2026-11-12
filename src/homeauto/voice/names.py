"""El nombre en castellano de cada equipo, y el alias que nombra lo que escribió una persona."""

from __future__ import annotations

import unicodedata
from typing import Iterable

# Cómo se escribe en castellano cada palabra conocida de un alias.
_WORDS = {
    "recamara": "recámara",
    "habitacion": "habitación",
    "comedor": "comedor",
    "living": "living",
    "cocina": "cocina",
    "bano": "baño",
    "jardin": "jardín",
    "estudio": "estudio",
    "oficina": "oficina",
    "dormitorio": "dormitorio",
    "cuarto": "cuarto",
    "patio": "patio",
    "quincho": "quincho",
    "sala": "sala",
}


def device_label(alias: str) -> str:
    """El alias como se le muestra a una persona: «recamara» → «Recámara»."""
    words = [_WORDS.get(word, word) for word in alias.split("_") if word]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def fold(text: str) -> str:
    """El texto sin mayúsculas ni tildes, para comparar nombres de equipo."""
    decomposed = unicodedata.normalize("NFD", text.strip().casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def find_alias(written: str, aliases: Iterable[str]) -> str | None:
    """El alias que nombra lo escrito, por alias o por nombre, o None."""
    wanted = fold(written)
    for alias in aliases:
        if wanted in (fold(alias), fold(device_label(alias))):
            return alias
    return None

"""Traducir un texto, para leerlo en el chat.

🔴 Nunca se dice en voz alta: Piper habla `es_AR` y lee cualquier otro idioma
con fonética española. Esto devuelve texto escrito y nada más.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

log = logging.getLogger(__name__)

# Traducir no es buscar ni reescribir: ni los seis segundos del pulido ni los
# sesenta de una pregunta.
TRANSLATE_TIMEOUT = 15

# Un mensaje de Telegram entra holgado; esto es para no mandar un libro.
MAX_TEXT = 1000
# Una traducción ocupa parecido al original. Mucho más que esto es otra cosa.
MAX_GROWTH = 4

DEFAULT_TARGET = "inglés si el texto está en español, o al español si no lo está"

# Lista cerrada a propósito: «al final no fui» empieza igual que «al francés» y
# un prefijo que también puede ser texto real se come parte del mensaje.
LANGUAGES = (
    "inglés", "ingles", "español", "espanol", "castellano", "portugués", "portugues",
    "francés", "frances", "italiano", "alemán", "aleman", "japonés", "japones",
    "chino", "ruso", "coreano", "catalán", "catalan", "gallego", "euskera",
    "neerlandés", "neerlandes", "holandés", "holandes", "árabe", "arabe", "hebreo",
    "polaco", "turco", "griego", "latín", "latin", "sueco", "noruego", "danés",
    "danes", "finés", "fines", "checo", "húngaro", "hungaro", "rumano",
    "ucraniano", "hindi", "vietnamita", "tailandés", "tailandes", "indonesio",
    "guaraní", "guarani", "quechua",
)

PROMPT = """Traducí este texto al {language}.

Reglas:
- Devolvé únicamente la traducción, sin comillas ni explicaciones.
- No agregues ni quites información.
- Si el texto ya está en ese idioma, devolvelo igual.

Texto: {text}"""

_PREFIX = re.compile(r"^(?:al|a|en)\s+([a-záéíóúñ]+)\s+(.+)$", re.IGNORECASE | re.DOTALL)


class TranslateError(Exception):
    """No se pudo traducir."""


class Translator:
    def __init__(self, model: Callable[[str], str], prompt: str = PROMPT):
        self.model = model
        self.prompt = prompt
        # Mismo texto y mismo idioma, misma respuesta.
        self._cache: dict[str, str] = {}

    def translate(self, text: str) -> str:
        """La traducción escrita, o `TranslateError` si no se pudo."""
        language, body = split_language(text)
        body = body.strip()
        if not body:
            raise TranslateError("Decime qué traduzco: /traducir hola")
        if len(body) > MAX_TEXT:
            raise TranslateError(f"Ese texto es muy largo: mandame hasta {MAX_TEXT} caracteres.")

        key = f"{language}\x00{body}"
        if key not in self._cache:
            self._cache[key] = self._ask(language or DEFAULT_TARGET, body)
        return self._cache[key]

    def _ask(self, language: str, body: str) -> str:
        try:
            answer = self.model(self.prompt.format(language=language, text=body))
        except Exception as exc:  # noqa: BLE001
            log.warning("no pude traducir: %s", exc)
            raise TranslateError(f"No pude traducir: {exc}") from exc

        answer = (answer or "").strip().strip('"«»')
        if not answer:
            raise TranslateError("El modelo no devolvió nada.")
        if len(answer) > max(len(body) * MAX_GROWTH, 80):
            raise TranslateError("Lo que volvió no parece una traducción.")
        return answer


def split_language(text: str) -> tuple[str, str]:
    """El idioma pedido adelante y el resto, o vacío y el texto entero."""
    match = _PREFIX.match(text.strip())
    if match and match.group(1).lower() in LANGUAGES:
        return match.group(1).lower(), match.group(2)
    return "", text

"""Pulir cómo suena lo que la casa va a decir, sin dejar que cambie los datos.

Todo lo que devuelve el modelo se valida antes de usarlo, y el original siempre
gana: sin clave, sin red, con una respuesta lenta o sospechosa, la casa dice el
texto que ya tenía. Por acá solo pasa texto que generamos nosotros.
"""

from __future__ import annotations

import base64

import logging
from typing import Callable, Iterable

from homeauto.verbalize import data_words

log = logging.getLogger(__name__)

# Lugar para reformular, no para narrar.
MAX_GROWTH = 1.6
MIN_SHRINK = 0.5

PROMPT = """Reescribí este aviso de voz para que suene natural dicho en voz alta,
en español rioplatense. Es para un parlante de una casa.

Reglas:
- No agregues ni quites información.
- No cambies ningún número, hora, momento del día ni nombre propio.
- Los números ya están escritos en palabras: dejalos exactamente como están.
- No uses dígitos.
- Una o dos oraciones. Nada de saludos, emojis ni comentarios tuyos.
- Respondé únicamente con el aviso reescrito.

Aviso: {text}"""


def as_is(text: str, must_keep: Iterable[str] = ()) -> str:
    """Lo de siempre: decir exactamente lo que se generó."""
    return text


class PolishError(Exception):
    """No se pudo llegar al modelo, o contestó algo inservible."""


class Polisher:
    def __init__(
        self,
        model: Callable[[str], str],
        prompt: str = PROMPT,
        max_growth: float = MAX_GROWTH,
        min_shrink: float = MIN_SHRINK,
    ):
        self.model = model
        self.prompt = prompt
        self.max_growth = max_growth
        self.min_shrink = min_shrink
        # Mismo texto, misma salida: VoiceSynth cachea por frase, y una
        # redacción distinta cada vez significaría sintetizar siempre.
        self._cache: dict[str, str] = {}

    def polish(self, text: str, must_keep: Iterable[str] = ()) -> str:
        if not text.strip():
            return text

        keep = tuple(must_keep)
        key = f"{text}\x00{'|'.join(keep)}"
        if key in self._cache:
            return self._cache[key]

        self._cache[key] = self._ask(text, keep)
        return self._cache[key]

    def _ask(self, text: str, must_keep: tuple[str, ...]) -> str:
        try:
            answer = self.model(self.prompt.format(text=text))
        except Exception as exc:  # noqa: BLE001 - nunca puede tumbar un aviso
            log.warning("no pude mejorar la redacción, va el texto original: %s", exc)
            return text

        answer = (answer or "").strip()
        problem = self._problem_with(text, answer, must_keep)
        if problem:
            log.info("descarto la reescritura (%s), va el texto original", problem)
            return text
        return answer

    def _problem_with(self, text: str, answer: str, must_keep: tuple[str, ...]) -> str:
        """Por qué no se puede confiar en la reescritura, o "" si se puede."""
        if not answer:
            return "vino vacía"
        if any(character.isdigit() for character in answer):
            return "trae dígitos"
        if len(answer) > len(text) * self.max_growth:
            return "se fue de largo"
        if len(answer) < len(text) * self.min_shrink:
            return "perdió contenido"
        if data_words(answer) != data_words(text):
            return "cambió un número o un momento del día"

        # Ignora mayúsculas: el modelo baja los títulos y eso no pierde ningún dato.
        lowered = answer.lower()
        missing = [term for term in must_keep if term and term.lower() not in lowered]
        if missing:
            return f"perdió {', '.join(missing)}"
        return ""


API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Nada de Gemma: razona antes de cada respuesta y la API rechaza los dos
# switches que lo apagarían, lo que cuesta decenas de segundos por reescritura.
DEFAULT_MODEL = "gemini-3.1-flash-lite"
# Nadie espera una reescritura. Pasado esto, el original es mejor que llegar tarde.
TIMEOUT = 6


def _post(url: str, **kwargs):
    """La llamada real. Se importa tarde para que los tests no toquen la red."""
    import requests

    return requests.post(url, **kwargs)


class GoogleModel:
    """Gemma por la API de Gemini: gratis y con un POST simple.

    Los modelos Gemma no aceptan system instruction, así que el prompt entero
    viaja como único turno de usuario.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        post: Callable[..., object] = _post,
        timeout: float = TIMEOUT,
        thinking: bool = False,
        search: bool = False,
    ):
        self.api_key = api_key
        self.model = model
        self.post = post
        self.timeout = timeout
        # Búsqueda en Google. Apagada para pulir y encendida para contestar
        # una pregunta.
        self.search = search
        # Los modelos que no dejan apagar el razonamiento vuelven esto a True,
        # así el pedido sigue siendo válido.
        self.thinking = thinking

    def _must_think(self) -> bool:
        """Razonamiento que no se puede apagar: Gemma siempre razona, y una
        búsqueda necesita el razonamiento para decidir qué buscar."""
        return self.search or self.model.startswith("gemma")

    def __call__(self, prompt: str, audio: bytes | None = None, mime: str = "") -> str:
        parts = [{"text": prompt}]
        if audio:
            parts.append(
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode("ascii")}}
            )
        body = {"contents": [{"parts": parts}]}
        if self.search:
            body["tools"] = [{"google_search": {}}]
        # Gemma contesta 400 a este switch en vez de ignorarlo.
        if not self.thinking and not self._must_think():
            body["generationConfig"] = {"thinkingConfig": {"thinkingBudget": 0}}

        try:
            response = self.post(
                API_URL.format(model=self.model),
                # En un header, nunca en la query string: la clave terminaría
                # en cualquier log que registre la URL.
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise PolishError(f"no pude consultar el modelo: {exc}") from exc

        blocked = (payload.get("promptFeedback") or {}).get("blockReason")
        if blocked:
            raise PolishError(f"la respuesta vino bloqueada: {blocked}")

        try:
            parts = payload["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise PolishError(f"respuesta inesperada del modelo: {exc}") from exc

        # Un modelo que razona devuelve el razonamiento en otra parte, marcada
        # `thought`. Se descarta.
        return "".join(
            part.get("text", "") for part in parts if not part.get("thought")
        ).strip()

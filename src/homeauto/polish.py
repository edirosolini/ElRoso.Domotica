"""Rewording what the house is about to say, without letting it change the facts.

The wording of a generated announcement is where a model helps: it turns
"Hoy tenés dos cosas. A las nueve y media de la mañana, Dentista." into
something a person would actually say. The facts are where it hurts, so
everything it gives back is checked before it is used.

🔴 The original always wins. This is decoration on a path that has to work:
no key, no network, a slow answer or a suspicious one, and the house says the
text it already had. Nothing here is allowed to leave anybody unwarned.

Only text *we* generate goes through here. What a person typed into /decir or
into a timer is said exactly as they wrote it.
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable

from homeauto.verbalize import data_words

log = logging.getLogger(__name__)

# Room to rephrase, not to start narrating. A model that rambles is a model
# that stopped rewording and started writing.
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
    """The default everywhere: say exactly what was generated."""
    return text


class PolishError(Exception):
    """The model could not be reached or answered something unusable."""


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
        # Same text in, same text out: VoiceSynth caches by phrase, and a
        # different wording every time would mean synthesizing every time.
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
        """Why the rewrite cannot be trusted, or "" when it can."""
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

        # Case-insensitive: the model lowercases titles, and that loses no fact.
        lowered = answer.lower()
        missing = [term for term in must_keep if term and term.lower() not in lowered]
        if missing:
            return f"perdió {', '.join(missing)}"
        return ""


API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# 🔴 Not Gemma. Gemma 4 reasons before every answer and will not stop: the API
# rejects both thinkingBudget and thinkingLevel for it. Measured against the
# real endpoint it took 40 to 79 seconds to reword one sentence, spending
# thousands of thinking tokens to emit twenty. Flash-Lite with thinking off
# answers the same thing in under two seconds.
DEFAULT_MODEL = "gemini-3.1-flash-lite"
# Nobody waits for prose. Past this the original is better than a late rewrite.
TIMEOUT = 6


def _post(url: str, **kwargs):
    """The real call. Imported lazily so tests never touch the network."""
    import requests

    return requests.post(url, **kwargs)


class GoogleModel:
    """Gemma through the Gemini API: free of charge, and a plain POST.

    The Gemma models take no system instruction, so the whole prompt travels
    as the single user turn.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        post: Callable[..., object] = _post,
        timeout: float = TIMEOUT,
        thinking: bool = False,
    ):
        self.api_key = api_key
        self.model = model
        self.post = post
        self.timeout = timeout
        # Rewording a sentence needs no deliberation, and the wait is the whole
        # cost. Models that refuse to have it turned off take this back to True
        # so the request stays valid — they are just too slow to be the default.
        self.thinking = thinking

    def _always_thinks(self) -> bool:
        return self.model.startswith("gemma")

    def __call__(self, prompt: str) -> str:
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        # Gemma answers 400 to the switch instead of ignoring it, which would
        # make every single rewrite fail quietly. Asked without it, it works —
        # just slowly, because it always reasons first.
        if not self.thinking and not self._always_thinks():
            body["generationConfig"] = {"thinkingConfig": {"thinkingBudget": 0}}

        try:
            response = self.post(
                API_URL.format(model=self.model),
                # 🔴 In a header, never in the query string: the key would end
                # up in every log that records the URL.
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

        # 🔴 A thinking model returns its reasoning as another part. Joining
        # them fed hundreds of words of deliberation to the speaker.
        return "".join(
            part.get("text", "") for part in parts if not part.get("thought")
        ).strip()

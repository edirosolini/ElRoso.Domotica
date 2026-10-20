"""Claude por la API de Anthropic, con la misma forma de llamarlo que `GoogleModel`."""

from __future__ import annotations

from typing import Callable

from homeauto.polish import TIMEOUT, PolishError

DEFAULT_MODEL = "claude-haiku-5-5"
# Lo que puede escribir una respuesta, razonamiento incluido.
MAX_TOKENS = 1024
SEARCH_MAX_TOKENS = 4096
# Vueltas de `pause_turn` antes de dar la respuesta por perdida.
MAX_TURNS = 3

WEB_SEARCH = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 3,
    "user_location": {
        "type": "approximate",
        "country": "AR",
        "city": "Buenos Aires",
        "timezone": "America/Argentina/Buenos_Aires",
    },
}


def anthropic_client(api_key: str, timeout: float):
    """El cliente real del SDK, sin reintentos y con el timeout de quien lo usa."""
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)


class ClaudeModel:
    """Un modelo de Claude que recibe un prompt y devuelve solo el texto de la respuesta."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = TIMEOUT,
        effort: str = "low",
        search: bool = False,
        make_client: Callable[[str, float], object] = anthropic_client,
    ):
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.effort = effort
        self.search = search
        self.make_client = make_client
        self._client = None

    def __call__(self, prompt: str, system: str = "") -> str:
        request = {
            "model": self.model,
            "max_tokens": SEARCH_MAX_TOKENS if self.search else MAX_TOKENS,
            "output_config": {"effort": self.effort},
        }
        if system:
            request["system"] = system
        if self.search:
            request["tools"] = [WEB_SEARCH]

        messages = [{"role": "user", "content": prompt}]
        pieces: list[str] = []
        for _ in range(MAX_TURNS):
            response = self._create(messages=messages, **request)
            if response.stop_reason == "refusal":
                raise PolishError("el modelo se negó a contestar")
            pieces.extend(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            )
            if response.stop_reason != "pause_turn":
                break
            # Se reenvía lo que dijo el asistente para que siga desde ahí.
            messages = [messages[0], {"role": "assistant", "content": response.content}]
        else:
            raise PolishError(f"la respuesta no terminó en {MAX_TURNS} vueltas")

        answer = "".join(pieces).strip()
        if not answer:
            raise PolishError("el modelo no devolvió texto")
        return answer

    def _create(self, **request):
        """Un pedido al SDK; cualquier error sale como PolishError."""
        try:
            if self._client is None:
                self._client = self.make_client(self._api_key, self.timeout)
            return self._client.messages.create(**request)
        except Exception as exc:  # noqa: BLE001
            raise PolishError(f"no pude consultar el modelo: {exc}") from exc

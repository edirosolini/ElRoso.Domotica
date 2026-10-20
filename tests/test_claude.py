"""El cliente de Claude, con el SDK reemplazado por un doble inyectado."""

from types import SimpleNamespace

import pytest

from homeauto import claude
from homeauto.claude import ClaudeModel
from homeauto.polish import PolishError, Polisher


def text(value):
    return SimpleNamespace(type="text", text=value)


def reply(*blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class FakeMessages:
    """Contesta lo que se le cargó y anota cada pedido."""

    def __init__(self, replies, fail=None):
        self.replies = list(replies)
        self.fail = fail
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise self.fail
        return self.replies.pop(0)


class FakeClient:
    def __init__(self, *replies, fail=None):
        self.messages = FakeMessages(replies, fail=fail)


def model_with(*replies, fail=None, **kwargs):
    client = FakeClient(*replies, fail=fail)
    built = []

    def make_client(api_key, timeout):
        built.append((api_key, timeout))
        return client

    model = ClaudeModel(api_key="sk-secreta", make_client=make_client, **kwargs)
    return model, client.messages.calls, built


def test_the_answer_comes_back():
    model, calls, _ = model_with(reply(text("mejor redactado")))

    assert model("un prompt") == "mejor redactado"
    assert calls[0]["messages"] == [{"role": "user", "content": "un prompt"}]


def test_the_model_and_a_low_effort_travel():
    model, calls, _ = model_with(reply(text("ok")), model="claude-haiku-5-5")

    model("prompt")

    sent = calls[0]
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["output_config"] == {"effort": "low"}
    assert sent["max_tokens"] > 0


def test_thinking_is_never_turned_off_by_hand():
    """En estos modelos mandar thinking deshabilitado puede dar un 400."""
    model, calls, _ = model_with(reply(text("ok")))

    model("prompt")

    assert "thinking" not in calls[0]


def test_the_system_travels_only_when_there_is_one():
    model, calls, _ = model_with(reply(text("ok")), reply(text("ok")))

    model("prompt")
    model("prompt", system="sos un parlante")

    assert "system" not in calls[0]
    assert calls[1]["system"] == "sos un parlante"


def test_without_search_no_tool_travels():
    model, calls, _ = model_with(reply(text("ok")))

    model("prompt")

    assert "tools" not in calls[0]


def test_with_search_the_web_tool_travels_from_buenos_aires():
    model, calls, _ = model_with(reply(text("ok")), search=True, effort="medium")

    model("prompt")

    sent = calls[0]
    assert sent["output_config"] == {"effort": "medium"}
    assert sent["tools"] == [
        {
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
    ]


def test_only_the_text_blocks_are_read():
    """El razonamiento y lo de la búsqueda no pueden llegar al parlante."""
    model, _, _ = model_with(
        reply(
            SimpleNamespace(type="thinking", thinking="pienso en voz alta"),
            SimpleNamespace(type="server_tool_use", name="web_search", input={}),
            SimpleNamespace(type="web_search_tool_result", content=[]),
            text("Ganó "),
            text("Boca."),
        )
    )

    assert model("prompt") == "Ganó Boca."


def test_a_paused_turn_is_continued_with_what_the_assistant_said():
    first = reply(
        SimpleNamespace(type="server_tool_use", name="web_search", input={}),
        text("Según lo que encontré, "),
        stop_reason="pause_turn",
    )
    model, calls, _ = model_with(first, reply(text("ganó Boca.")), search=True)

    assert model("prompt") == "Según lo que encontré, ganó Boca."
    assert len(calls) == 2
    assert calls[1]["messages"] == [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": first.content},
    ]


def test_a_turn_that_never_ends_gives_up():
    paused = [reply(text("..."), stop_reason="pause_turn") for _ in range(10)]
    model, calls, _ = model_with(*paused, search=True)

    with pytest.raises(PolishError):
        model("prompt")
    assert len(calls) == claude.MAX_TURNS


def test_a_refusal_is_a_polish_error():
    model, _, _ = model_with(reply(text("No puedo."), stop_reason="refusal"))

    with pytest.raises(PolishError):
        model("prompt")


def test_an_sdk_error_is_a_polish_error():
    model, _, _ = model_with(fail=RuntimeError("APIConnectionError"))

    with pytest.raises(PolishError):
        model("prompt")


def test_an_answer_without_text_is_a_polish_error():
    model, _, _ = model_with(reply(SimpleNamespace(type="thinking", thinking="mmm")))

    with pytest.raises(PolishError):
        model("prompt")


def test_a_failed_search_without_text_is_a_polish_error():
    """El error de la herramienta llega como un bloque, no como excepción."""
    failed = SimpleNamespace(
        type="web_search_tool_result",
        content=SimpleNamespace(type="web_search_tool_result_error", error_code="unavailable"),
    )
    model, _, _ = model_with(reply(failed), search=True)

    with pytest.raises(PolishError):
        model("prompt")


def test_the_client_is_built_once_with_the_key_and_the_timeout():
    model, _, built = model_with(reply(text("a")), reply(text("b")), timeout=6)

    model("uno")
    model("dos")

    assert built == [("sk-secreta", 6)]


def test_building_the_model_does_not_build_the_client():
    """Armar el cableado no puede salir a la red ni pedir el SDK."""
    _, _, built = model_with()

    assert built == []


def test_the_real_client_gives_up_quickly_and_does_not_retry():
    """El pulido corta a los seis segundos: los reintentos del SDK no entran."""
    client = claude.anthropic_client("sk-secreta", 6)

    try:
        assert client.timeout == 6
        assert client.max_retries == 0
    finally:
        client.close()


def test_the_key_is_not_in_the_repr():
    model, _, _ = model_with()

    assert "sk-secreta" not in repr(model)


def test_a_polisher_backed_by_claude_keeps_the_original_on_failure():
    model, _, _ = model_with(fail=TimeoutError("timeout"))
    original = "Hoy tenés dos cosas."

    assert Polisher(model=model).polish(original) == original

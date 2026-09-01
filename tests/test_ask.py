"""Preguntas contestadas en voz alta.

🔴 La regla que manda acá es la misma de todo el proyecto: nada que vaya al
sintetizador puede llevar un dígito. Una respuesta de búsqueda está llena de
años, cifras y resultados, así que lo escrito y lo hablado no son lo mismo.
"""

import pytest

from homeauto.ask import Asker, AskError, NOT_SPOKEN


def model_saying(reply):
    def model(prompt):
        model.prompts.append(prompt)
        return reply
    model.prompts = []
    return model


def model_failing(exc):
    def model(_prompt):
        raise exc
    return model


BIEN = (
    "RESPUESTA: Los diez mejores goles de Messi según la mayoría de las listas "
    "incluyen el gol al Getafe de 2007 y el gol al Athletic en la final de 2015.\n"
    "VOZ: Te armé la lista de los diez mejores goles de Messi; encabeza el del Getafe."
)


def test_the_answer_comes_back_split_in_two():
    asker = Asker(model_saying(BIEN))

    answer = asker.ask("top 10 de los mejores goles de Messi")

    assert "2007" in answer.written, "lo escrito conserva los datos"
    assert answer.spoken.startswith("Te armé la lista")


def test_nothing_spoken_ever_carries_a_digit():
    """🔴 Piper lee un dígito como cardinal masculino suelto."""
    asker = Asker(model_saying(BIEN))

    answer = asker.ask("top 10 de goles")

    assert not any(c.isdigit() for c in answer.spoken), answer.spoken


def test_a_spoken_half_with_digits_is_not_spoken():
    sucia = "RESPUESTA: Messi hizo 672 goles.\nVOZ: Messi hizo 672 goles."
    asker = Asker(model_saying(sucia))

    answer = asker.ask("cuántos goles hizo Messi")

    assert answer.spoken == NOT_SPOKEN
    assert "672" in answer.written, "la respuesta completa igual llega al chat"


def test_an_answer_without_tags_is_written_but_not_spoken():
    """Si el modelo no respeta el formato, se lee en el chat y no se inventa voz."""
    asker = Asker(model_saying("Messi hizo un montón de goles."))

    answer = asker.ask("goles")

    assert answer.written == "Messi hizo un montón de goles."
    assert answer.spoken == NOT_SPOKEN


def test_a_spoken_half_that_runs_long_is_not_spoken():
    """Un top diez dicho entero es un minuto de parlante. El chat lo aguanta; la casa no."""
    largo = "RESPUESTA: corto.\nVOZ: " + ("palabra " * 200)
    asker = Asker(model_saying(largo))

    assert asker.ask("algo").spoken == NOT_SPOKEN


def test_the_tags_survive_markdown_and_case():
    """Los modelos devuelven los rótulos en negrita cuando se les canta la gana."""
    asker = Asker(model_saying("**Respuesta:** dos cosas.\n**Voz:** son dos cosas."))

    answer = asker.ask("qué")

    assert answer.written == "dos cosas."
    assert answer.spoken == "son dos cosas."


def test_an_empty_question_is_refused():
    asker = Asker(model_saying(BIEN))

    with pytest.raises(AskError):
        asker.ask("   ")


def test_a_model_failure_becomes_an_ask_error():
    """No hay original al que volver: una pregunta sin respuesta no tiene respaldo."""
    asker = Asker(model_failing(RuntimeError("timeout")))

    with pytest.raises(AskError):
        asker.ask("algo")


def test_an_empty_answer_becomes_an_ask_error():
    asker = Asker(model_saying("   "))

    with pytest.raises(AskError):
        asker.ask("algo")


def test_only_the_spoken_tag_still_leaves_something_written():
    """Nunca se contesta al chat con la nada."""
    asker = Asker(model_saying("VOZ: son dos cosas."))

    answer = asker.ask("qué")

    assert answer.written == "son dos cosas."
    assert answer.spoken == "son dos cosas."


def test_the_question_reaches_the_model_verbatim():
    """⚠️ La pregunta es de una persona: no se reescribe, igual que /decir."""
    model = model_saying(BIEN)

    Asker(model).ask("top 10 de los mejores goles de Messi")

    assert "top 10 de los mejores goles de Messi" in model.prompts[0]


def test_the_written_half_is_capped_for_telegram():
    """Telegram rechaza un mensaje de más de 4096 caracteres."""
    largo = "RESPUESTA: " + ("dato " * 2000) + "\nVOZ: son muchos datos."
    asker = Asker(model_saying(largo), max_written=100)

    answer = asker.ask("algo")

    assert len(answer.written) == 100
    assert answer.spoken == "son muchos datos.", "recortar lo escrito no toca lo hablado"


def test_a_short_answer_is_said_whole():
    """🔴 Resumir un chiste lo pasa a estilo indirecto y deja de ser un chiste.

    Pasó de verdad: «—Papá, ¿qué se siente tener un hijo tan lindo? —No sé,
    preguntale a tu abuelo» volvió al parlante como «un pibe le pregunta al
    padre qué se siente... y el papá le responde que no sabe».
    """
    chiste = (
        "RESPUESTA: ¿Sabés cómo se despiden los químicos? Ácido un placer.\n"
        "VOZ: ¿Sabés cómo se despiden los químicos? Ácido un placer."
    )
    answer = Asker(model_saying(chiste)).ask("contame un chiste")

    assert answer.spoken == answer.written


def test_the_prompt_tells_it_not_to_summarize_a_short_answer():
    """El prompt es lo único que sostiene esto: se verifica que siga diciéndolo."""
    from homeauto.ask import PROMPT

    bajado = PROMPT.lower()
    assert "entera" in bajado or "completa" in bajado
    assert "chiste" in bajado, "el caso que rompió tiene que estar nombrado en el prompt"

"""Interpretar un mensaje suelto, sin barra adelante.

El router no ejecuta nada: decide qué comando quiso decir la persona y con qué
argumento. Quien ejecuta es `Commands`, que ya sabe hacerlo.
"""

import pytest

from homeauto.route import ROUTABLE, RouteError, Router


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


def test_a_plain_request_becomes_a_command():
    router = Router(model_saying("COMANDO: timer\nARGUMENTO: 10m sacá la pizza"))

    decision = router.route("poneme un timer de 10 minutos para sacar la pizza")

    assert decision.command == "timer"
    assert decision.argument == "10m sacá la pizza"


def test_a_question_is_not_a_command():
    router = Router(model_saying("COMANDO: ninguno\nARGUMENTO:"))

    decision = router.route("cuántos goles hizo Messi")

    assert decision.command is None
    assert decision.is_question


def test_a_command_nobody_registered_is_treated_as_a_question():
    """El modelo puede devolver cualquier cosa; solo se acepta lo que existe."""
    router = Router(model_saying("COMANDO: lanzar_misiles\nARGUMENTO: ya"))

    assert router.route("hacé algo").is_question


def test_every_routable_command_exists():
    from homeauto.main import ALL_COMMANDS

    assert set(ROUTABLE) <= set(ALL_COMMANDS)


def test_the_message_reaches_the_model_whole():
    model = model_saying("COMANDO: ninguno\nARGUMENTO:")

    Router(model).route("apagá la tele del comedor")

    assert "apagá la tele del comedor" in model.prompts[0]


def test_the_tags_survive_markdown_and_case():
    router = Router(model_saying("**Comando:** Timer\n**Argumento:** 5m café"))

    decision = router.route("avisame en 5 minutos lo del café")

    assert decision.command == "timer"
    assert decision.argument == "5m café"


def test_an_unparseable_reply_is_a_question():
    router = Router(model_saying("no sé qué quiso decir"))

    assert router.route("algo").is_question


def test_a_model_failure_is_not_silently_a_question():
    """Tragarse el fallo mandaría a buscar en internet un pedido de apagar la tele."""
    router = Router(model_failing(RuntimeError("timeout")))

    with pytest.raises(RouteError):
        router.route("apagá la tele")


def test_an_empty_message_is_refused():
    router = Router(model_saying("COMANDO: ninguno\nARGUMENTO:"))

    with pytest.raises(RouteError):
        router.route("   ")


# --- 🔴 el payload de /decir es de una persona y va literal ------------------


def test_what_is_said_out_loud_has_to_come_from_the_message():
    """El modelo no puede reescribir lo que la casa va a decir con voz propia."""
    router = Router(model_saying("COMANDO: decir\nARGUMENTO: Ya llegué a casa"))

    decision = router.route("decí que ya llegué")

    assert decision.is_question, "«Ya llegué a casa» no está en el mensaje original"


def test_a_faithful_payload_is_accepted():
    router = Router(model_saying("COMANDO: decir\nARGUMENTO: que ya llegué"))

    decision = router.route("decí que ya llegué")

    assert decision.command == "decir"
    assert decision.argument == "que ya llegué"


def test_the_payload_check_ignores_case_and_spacing():
    router = Router(model_saying("COMANDO: decir\nARGUMENTO: la  comida está lista"))

    decision = router.route("decile a todos que La comida está lista")

    assert decision.command == "decir"


def test_the_target_prefix_may_be_added_to_what_is_said():
    """«en comedor» lo arma el router, no la persona: es destino, no mensaje."""
    router = Router(model_saying("COMANDO: decir\nARGUMENTO: en comedor la comida está lista"))

    decision = router.route("decí en el comedor que la comida está lista")

    assert decision.command == "decir"
    assert decision.argument == "en comedor la comida está lista"


def test_the_words_of_a_thread_are_also_the_words_of_the_person():
    """🔴 En una conversación, lo fiel se mide contra el hilo entero.

    La respuesta llega en el mensaje de después: si la fidelidad se midiera
    contra el último renglón, «que bajen a comer» no estaría y la casa se
    quedaría sin decir algo que la persona sí escribió.
    """
    router = Router(model_saying("COMANDO: decir\nARGUMENTO: que bajen a comer"))

    decision = router.route("quiero que digas algo\nque bajen a comer")

    assert decision.command == "decir"
    assert decision.argument == "que bajen a comer"


def test_what_nobody_wrote_in_the_thread_is_still_invented():
    router = Router(model_saying("COMANDO: decir\nARGUMENTO: la cena está lista"))

    assert router.route("quiero que digas algo\nque bajen a comer").is_question

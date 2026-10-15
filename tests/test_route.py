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


def test_every_routable_command_is_described_in_the_prompt():
    """Un comando que el prompt no nombra existe, pero el modelo no lo elige nunca."""
    from homeauto.route import PROMPT

    missing = [name for name in ROUTABLE if f"- {name}:" not in PROMPT]
    assert missing == []


def test_postponing_is_routable():
    router = Router(model_saying("COMANDO: posponer\nARGUMENTO: 5m"))

    decision = router.route("posponé la alarma cinco minutos")

    assert decision.command == "posponer"
    assert decision.argument == "5m"


def test_the_prompt_does_not_convert_times_inside_what_is_said():
    """Sin la excepción, «salgo en cinco minutos» volvía como «salgo en 5m» y se descartaba."""
    from homeauto.route import PROMPT

    start = PROMPT.index("Las duraciones y horas")
    rule = PROMPT[start:PROMPT.index("\n\n", start)]
    assert "timer" in rule and "recordar" in rule
    assert "En decir y\n  llamar no" in rule


def test_the_prompt_names_the_monthly_form():
    from homeauto.route import PROMPT

    assert '"mensual 10 9:00 pagar la luz"' in PROMPT
    assert (
        "Mensaje: recordame el 10 de cada mes a las nueve pagar la luz\n"
        "COMANDO: recordar\n"
        "ARGUMENTO: mensual 10 9:00 pagar la luz"
    ) in PROMPT


def test_the_router_measurement_covers_the_monthly_form():
    from deploy.measure_router import CASES

    assert ("recordame el 10 de cada mes a las nueve pagar la luz", "recordar", "mensual 10") in CASES


def test_the_prompt_names_the_working_days_that_skip_holidays():
    from homeauto.route import PROMPT

    assert '"hábiles 7:00 salida al colegio"' in PROMPT
    assert "feriados" in PROMPT


def test_the_router_measurement_covers_the_working_days():
    from deploy.measure_router import CASES

    assert (
        "recordame los días hábiles a las siete salida al colegio", "recordar", "hábiles"
    ) in CASES


def test_the_pills_are_routable():
    assert "pastillas" in ROUTABLE


def test_the_prompt_names_the_restock_of_the_pills():
    from homeauto.route import PROMPT

    assert (
        "Mensaje: compré 30 de enalapril\n"
        "COMANDO: pastillas\n"
        "ARGUMENTO: enalapril +30"
    ) in PROMPT


def test_buying_pills_is_routed_to_the_restock():
    router = Router(model_saying("COMANDO: pastillas\nARGUMENTO: enalapril +30"))

    decision = router.route("compré 30 de enalapril")

    assert (decision.command, decision.argument) == ("pastillas", "enalapril +30")


def test_the_router_measurement_covers_the_pills():
    from deploy.measure_router import CASES

    assert ("compré 30 de enalapril", "pastillas", "enalapril +30") in CASES


def test_the_vacations_are_routable():
    assert "vacaciones" in ROUTABLE


def test_the_prompt_turns_the_return_date_into_day_and_month():
    from homeauto.route import PROMPT

    start = PROMPT.index("- vacaciones:")
    line = PROMPT[start:PROMPT.index("\n- ", start + 1)]
    assert '"hasta 25/10"' in line
    assert "dd/mm" in PROMPT
    assert (
        "Mensaje: nos vamos de vacaciones hasta el 25 de octubre\n"
        "COMANDO: vacaciones\n"
        "ARGUMENTO: hasta 25/10"
    ) in PROMPT


def test_going_on_vacation_is_routed_with_its_date():
    router = Router(model_saying("COMANDO: vacaciones\nARGUMENTO: hasta 25/10"))

    decision = router.route("nos vamos de vacaciones hasta el 25 de octubre")

    assert (decision.command, decision.argument) == ("vacaciones", "hasta 25/10")


def test_the_router_measurement_covers_the_vacations_and_their_lookalike():
    from deploy.measure_router import CASES

    assert (
        "nos vamos de vacaciones hasta el 25 de octubre", "vacaciones", "hasta 25/10"
    ) in CASES
    assert any(
        message == "recordame comprar los pasajes de las vacaciones" and command == "recordar"
        for message, command, _ in CASES
    )

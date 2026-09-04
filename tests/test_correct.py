"""Corregir lo que escribió una persona, sin cambiar lo que dijo.

🔴 No es el pulidor. El pulidor reescribe; esto arregla cómo está escrito y
nada más: mismas palabras, en el mismo orden. Lo único que puede crecer es un
número, porque un dígito dicho por Piper suena mal ("uno minuto").
"""

from homeauto.correct import Corrector, as_written


def model_saying(reply):
    def model(prompt):
        model.prompts.append(prompt)
        return reply
    model.prompts = []
    return model


def model_failing(exc=RuntimeError("sin red")):
    def model(_prompt):
        raise exc
    return model


def test_the_fallback_says_exactly_what_was_written():
    assert as_written("decí que ya llegué") == "decí que ya llegué"


def test_accents_and_capitals_come_back():
    fixed = Corrector(model_saying("Decí que ya llegué.")).correct("deci que ya llegue")

    assert fixed == "Decí que ya llegué."


def test_a_chat_abbreviation_is_expanded():
    corrector = Corrector(model_saying("Avisales que ya está la comida."))

    assert corrector.correct("avisales q ya esta la comida") == "Avisales que ya está la comida."


def test_a_digit_becomes_words():
    """El motivo de todo esto: Piper lee «1 minuto» como «uno minuto»."""
    corrector = Corrector(model_saying("Llego en un minuto."))

    assert corrector.correct("llego en 1 minuto") == "Llego en un minuto."


def test_an_hour_may_grow_into_its_words():
    corrector = Corrector(model_saying("La reunión es a las nueve de la noche."))

    assert corrector.correct("la reunion es a las 21") == "La reunión es a las nueve de la noche."


def test_a_typo_in_a_long_word_is_fixed():
    corrector = Corrector(model_saying("Ya está la comida."))

    assert corrector.correct("ya esta la comidaa") == "Ya está la comida."


def test_a_short_word_is_never_swapped_for_another():
    """«no» y «yo» están a una letra: ahí no se corrige, se respeta."""
    original = "no voy a ir"
    corrector = Corrector(model_saying("Yo voy a ir."))

    assert corrector.correct(original) == original


def test_a_word_that_nobody_wrote_is_rejected():
    original = "avisá que llego"
    corrector = Corrector(model_saying("Avisá a todos que ya llego."))

    assert corrector.correct(original) == original


def test_a_word_that_disappeared_is_rejected():
    original = "avisá que llego tarde"
    corrector = Corrector(model_saying("Avisá que llego."))

    assert corrector.correct(original) == original


def test_a_reordered_sentence_is_rejected():
    original = "la comida ya está"
    corrector = Corrector(model_saying("Ya está la comida."))

    assert corrector.correct(original) == original


def test_an_answer_with_digits_is_rejected():
    """Lo corregido se sintetiza: un dígito ahí es el bug que veníamos a tapar."""
    original = "llego en 1 minuto"
    corrector = Corrector(model_saying("Llego en 1 minuto."))

    assert corrector.correct(original) == original


def test_a_number_that_turns_into_a_speech_is_rejected():
    original = "llego en 5"
    corrector = Corrector(
        model_saying("Llego en cinco minutos contados desde este preciso instante, avisá.")
    )

    assert corrector.correct(original) == original


def test_an_empty_answer_leaves_the_text_alone():
    original = "decí que ya llegué"

    assert Corrector(model_saying("   ")).correct(original) == original


def test_a_model_that_falls_over_never_costs_a_message():
    """🔴 El original siempre gana: esto es decoración sobre algo que ya funciona."""
    original = "decí que ya llegué"

    assert Corrector(model_failing()).correct(original) == original


def test_nothing_to_correct_costs_no_call():
    model = model_saying("lo que sea")

    assert Corrector(model).correct("   ") == "   "
    assert model.prompts == []


def test_the_same_text_is_only_corrected_once():
    """Se cachea, o se rompe el cache de síntesis: VoiceSynth cachea por frase."""
    model = model_saying("Decí que ya llegué.")
    corrector = Corrector(model)

    corrector.correct("deci que ya llegue")
    corrector.correct("deci que ya llegue")

    assert len(model.prompts) == 1


def test_the_prompt_carries_the_text_and_forbids_rewriting():
    model = model_saying("Hola.")
    Corrector(model).correct("hola")

    prompt = model.prompts[0]
    assert "hola" in prompt
    assert "No cambies" in prompt or "no cambies" in prompt


def at(hour, minute=0):
    from datetime import datetime

    return lambda: datetime(2026, 9, 4, hour, minute)


def test_a_meal_follows_the_clock():
    """El ejemplo del dueño: a las nueve y media de la noche, comer es cenar."""
    corrector = Corrector(model_saying("Diego, es hora de cenar."), clock=at(21, 30))

    assert corrector.correct("Diego es hoa de comer") == "Diego, es hora de cenar."


def test_the_same_message_at_noon_is_lunch():
    corrector = Corrector(model_saying("Diego, es hora de almorzar."), clock=at(12, 30))

    assert corrector.correct("Diego es hoa de comer") == "Diego, es hora de almorzar."


def test_the_prompt_says_what_time_it_is():
    model = model_saying("Hola.")
    Corrector(model, clock=at(21, 30)).correct("hola")

    assert "21:30" in model.prompts[0]
    assert "la cena" in model.prompts[0]


def test_only_a_meal_may_become_another_word():
    """La licencia es de las comidas, no de cualquier verbo."""
    original = "es hora de salir"
    corrector = Corrector(model_saying("Es hora de cenar."), clock=at(21))

    assert corrector.correct(original) == original


def test_a_meal_does_not_become_anything_else():
    original = "es hora de comer"
    corrector = Corrector(model_saying("Es hora de irse."), clock=at(21))

    assert corrector.correct(original) == original


def test_the_cache_does_not_serve_lunch_at_night():
    """La comida entra en la clave: la misma frase a otra hora es otra corrección."""
    replies = ["Es hora de almorzar.", "Es hora de cenar."]
    moment = [at(12)()]

    def model(_prompt):
        return replies.pop(0)

    from homeauto.correct import Corrector as C

    corrector = C(model, clock=lambda: moment[0])
    assert corrector.correct("es hora de comer") == "Es hora de almorzar."

    moment[0] = at(21)()
    assert corrector.correct("es hora de comer") == "Es hora de cenar."


def test_a_three_letter_typo_is_still_a_typo():
    corrector = Corrector(model_saying("Es hora."), clock=at(21))

    assert corrector.correct("es hoa") == "Es hora."


def test_the_meal_of_each_hour():
    from homeauto.correct import meal_at
    from datetime import datetime

    hours = {8: "el desayuno", 13: "el almuerzo", 17: "la merienda", 22: "la cena", 3: "la cena"}
    for hour, meal in hours.items():
        assert meal_at(datetime(2026, 9, 4, hour)) == meal

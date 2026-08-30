"""Polishing generated wording without letting the model touch the facts."""

import pytest

from homeauto.polish import PolishError, Polisher


class FakeModel:
    """Stands in for the API: returns canned answers, records the prompts."""

    def __init__(self, *answers, fail=False):
        self.answers = list(answers)
        self.fail = fail
        self.prompts = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.fail:
            raise PolishError("la API no contestó")
        return self.answers.pop(0) if self.answers else ""


def polisher(*answers, **kwargs):
    return Polisher(model=FakeModel(*answers), **kwargs)


ORIGINAL = "Hoy tenés dos cosas. A las nueve y media de la mañana, Dentista."


def test_a_better_wording_is_used():
    better = "Hoy tenés dos cosas. A las nueve y media de la mañana vas al Dentista."

    assert polisher(better).polish(ORIGINAL, must_keep=["Dentista"]) == better


def test_the_original_wins_when_the_model_fails():
    model = FakeModel(fail=True)

    assert Polisher(model=model).polish(ORIGINAL) == ORIGINAL


def test_the_original_wins_on_an_empty_answer():
    assert polisher("   ").polish(ORIGINAL) == ORIGINAL


def test_a_digit_in_the_answer_is_rejected():
    """Los números ya van en palabras; un dígito volvería a sonar mal."""
    assert polisher("Hoy tenés 2 cosas, a las 9:30, Dentista.").polish(ORIGINAL) == ORIGINAL


def test_changing_a_number_is_rejected():
    """🔴 Lo peor que puede hacer: moverte la hora."""
    tampered = "Hoy tenés dos cosas. A las diez y media de la mañana, Dentista."

    assert polisher(tampered).polish(ORIGINAL) == ORIGINAL


def test_dropping_a_number_is_rejected():
    assert polisher("Hoy tenés cosas. Dentista a la mañana.").polish(ORIGINAL) == ORIGINAL


def test_losing_a_term_that_must_survive_is_rejected():
    reworded = "Hoy tenés dos cosas. A las nueve y media de la mañana, el turno."

    assert polisher(reworded).polish(ORIGINAL, must_keep=["Dentista"]) == ORIGINAL


def test_an_answer_that_rambles_is_rejected():
    rambling = ORIGINAL + " " + "Y además te recuerdo que deberías descansar bien. " * 6

    assert polisher(rambling).polish(ORIGINAL) == ORIGINAL


def test_the_answer_is_cached_so_the_audio_cache_still_works():
    model = FakeModel("Hoy tenés dos cosas. A las nueve y media de la mañana, Dentista, ahí.")
    subject = Polisher(model=model)

    first = subject.polish(ORIGINAL)
    second = subject.polish(ORIGINAL)

    assert first == second
    assert len(model.prompts) == 1, "una sola llamada para el mismo texto"


def test_the_text_to_polish_reaches_the_model():
    model = FakeModel(ORIGINAL)
    Polisher(model=model).polish(ORIGINAL)

    assert ORIGINAL in model.prompts[0]


def test_empty_text_is_left_alone_without_calling_the_model():
    model = FakeModel()

    assert Polisher(model=model).polish("   ") == "   "
    assert model.prompts == []


# --- el cliente real de Google, sin salir a la red ---

from homeauto.polish import GoogleModel


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def answer(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_the_google_client_returns_the_answer():
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(answer("mejor redactado"))

    model = GoogleModel(api_key="secreta", post=post)

    assert model("un prompt") == "mejor redactado"
    url, kwargs = calls[0]
    assert "gemma" in url
    assert kwargs["json"]["contents"][0]["parts"][0]["text"] == "un prompt"


def test_the_key_travels_in_a_header_not_in_the_url():
    """En la URL terminaría en cualquier log que registre el request."""
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(answer("ok"))

    GoogleModel(api_key="secreta", post=post)("un prompt")
    url, kwargs = calls[0]

    assert "secreta" not in url
    assert kwargs["headers"]["x-goog-api-key"] == "secreta"


def test_the_client_gives_up_quickly():
    """Un aviso no puede esperar a que el modelo se despierte."""
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs)
        return FakeResponse(answer("ok"))

    GoogleModel(api_key="k", post=post, timeout=4)("prompt")

    assert calls[0]["timeout"] == 4


def test_an_http_error_becomes_a_polish_error():
    def post(url, **kwargs):
        return FakeResponse({}, status=429)

    with pytest.raises(PolishError):
        GoogleModel(api_key="k", post=post)("prompt")


def test_an_answer_without_candidates_becomes_a_polish_error():
    def post(url, **kwargs):
        return FakeResponse({"candidates": []})

    with pytest.raises(PolishError):
        GoogleModel(api_key="k", post=post)("prompt")


def test_a_blocked_answer_becomes_a_polish_error():
    def post(url, **kwargs):
        return FakeResponse({"promptFeedback": {"blockReason": "SAFETY"}})

    with pytest.raises(PolishError):
        GoogleModel(api_key="k", post=post)("prompt")


def test_the_model_id_can_be_changed():
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return FakeResponse(answer("ok"))

    GoogleModel(api_key="k", model="gemma-4-31b-it", post=post)("prompt")

    assert "gemma-4-31b-it" in calls[0]


def test_a_polisher_backed_by_google_falls_back_on_failure():
    """De punta a punta: si la API falla, se dice el texto original."""
    def post(url, **kwargs):
        raise OSError("sin red")

    subject = Polisher(model=GoogleModel(api_key="k", post=post))

    assert subject.polish(ORIGINAL) == ORIGINAL

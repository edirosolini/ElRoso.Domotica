"""Los feriados argentinos: de argentinadatos a una caché local que se lee sin red."""

import re
import sqlite3
from datetime import date

import pytest

from homeauto.holidays import (
    BRIDGE,
    FIXED,
    MOVABLE,
    URL,
    Holiday,
    HolidayClient,
    HolidayError,
    HolidayStore,
    clean_name,
    refresh,
    spoken_name,
)

PAYLOAD_2026 = [
    {"fecha": "2026-01-01", "tipo": "inamovible", "nombre": "Año nuevo"},
    {"fecha": "2026-06-15", "tipo": "trasladable", "nombre": "Paso a la Inmortalidad del General Martín Miguel de Güemes (17/6)"},
    {"fecha": "2026-07-10", "tipo": "puente", "nombre": "Puente turístico no laborable"},
    {"fecha": "2026-10-12", "tipo": "trasladable", "nombre": "Día del Respeto a la Diversidad Cultural"},
]
PAYLOAD_2027 = [{"fecha": "2027-01-01", "tipo": "inamovible", "nombre": "Año nuevo"}]


class Fetch:
    """Contesta por año y anota qué se pidió; un año en `broken` falla."""

    def __init__(self, payloads=None, broken=()):
        self.payloads = payloads or {2026: PAYLOAD_2026, 2027: PAYLOAD_2027}
        self.broken = set(broken)
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        year = int(url.rstrip("/").rsplit("/", 1)[1])
        if year in self.broken:
            raise ConnectionError("sin red")
        return self.payloads.get(year, [])


@pytest.fixture
def store(tmp_path):
    return HolidayStore(tmp_path / "jobs.db")


# --- el nombre ---


def test_the_date_in_parentheses_is_dropped_from_the_name():
    assert clean_name("Paso a la Inmortalidad del General Güemes (17/6)") == (
        "Paso a la Inmortalidad del General Güemes"
    )


def test_a_name_without_parentheses_stays_as_it_is():
    assert clean_name("Año nuevo") == "Año nuevo"


# --- el feriado ---


def test_fixed_and_movable_holidays_skip_and_a_bridge_does_not():
    assert Holiday(date(2026, 1, 1), FIXED, "Año nuevo").skips
    assert Holiday(date(2026, 10, 12), MOVABLE, "Diversidad").skips
    assert not Holiday(date(2026, 7, 10), BRIDGE, "Puente").skips


def test_a_holiday_is_said_with_its_reason():
    holiday = Holiday(date(2026, 1, 1), FIXED, "Año nuevo")

    assert holiday.spoken == "Hoy es feriado: Año nuevo."
    assert holiday.written == "Hoy es feriado: Año nuevo."


def test_a_name_with_digits_is_only_written():
    holiday = Holiday(date(2026, 4, 2), FIXED, "Día del Veterano y de los Caídos en Malvinas 1982")

    assert holiday.spoken == "Hoy es feriado."
    assert "1982" in holiday.written
    assert not re.search(r"\d", holiday.spoken)


def test_a_bridge_is_a_non_working_day():
    holiday = Holiday(date(2026, 7, 10), BRIDGE, "Puente turístico no laborable")

    assert holiday.spoken == "Hoy es día no laborable."
    assert not holiday.skips


# --- el cliente ---


def test_the_client_asks_for_the_year_and_cleans_the_names():
    fetch = Fetch()

    found = HolidayClient(fetch=fetch).year(2026)

    assert fetch.urls == [URL.format(year=2026)]
    assert found[1] == Holiday(
        date(2026, 6, 15), MOVABLE, "Paso a la Inmortalidad del General Martín Miguel de Güemes"
    )
    assert [holiday.kind for holiday in found] == [FIXED, MOVABLE, BRIDGE, MOVABLE]


def test_a_client_that_cannot_reach_the_api_raises():
    with pytest.raises(HolidayError):
        HolidayClient(fetch=Fetch(broken={2026})).year(2026)


def test_a_payload_that_does_not_make_sense_raises():
    with pytest.raises(HolidayError):
        HolidayClient(fetch=lambda url: [{"fecha": "mañana"}]).year(2026)


def test_requests_is_imported_inside_the_function():
    import homeauto.holidays as module

    assert "requests" not in vars(module)


# --- la caché ---


def test_the_store_has_its_own_table(store):
    with sqlite3.connect(store.db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}

    assert "holidays" in tables


def test_the_store_answers_by_day_without_the_network(store):
    store.replace(2026, HolidayClient(fetch=Fetch()).year(2026))

    assert store.get(date(2026, 1, 1)).name == "Año nuevo"
    assert store.get(date(2026, 1, 2)) is None


def test_the_store_lists_a_range(store):
    store.replace(2026, HolidayClient(fetch=Fetch()).year(2026))

    found = store.between(date(2026, 6, 1), date(2026, 7, 11))

    assert [holiday.day for holiday in found] == [date(2026, 6, 15), date(2026, 7, 10)]


def test_replacing_a_year_leaves_the_others(store):
    client = HolidayClient(fetch=Fetch())
    store.replace(2026, client.year(2026))
    store.replace(2027, client.year(2027))
    store.replace(2026, [Holiday(date(2026, 5, 1), FIXED, "Día del trabajador")])

    assert store.get(date(2026, 1, 1)) is None
    assert store.get(date(2026, 5, 1)).name == "Día del trabajador"
    assert store.get(date(2027, 1, 1)).name == "Año nuevo"


# --- el refresco ---


def test_before_november_only_the_current_year_is_fetched(store):
    fetch = Fetch()

    refresh(HolidayClient(fetch=fetch), store, date(2026, 10, 15))

    assert fetch.urls == [URL.format(year=2026)]
    assert store.get(date(2026, 1, 1)) is not None


def test_from_november_the_next_year_is_fetched_too(store):
    fetch = Fetch()

    refresh(HolidayClient(fetch=fetch), store, date(2026, 11, 1))

    assert fetch.urls == [URL.format(year=2026), URL.format(year=2027)]
    assert store.get(date(2027, 1, 1)) is not None


def test_a_failed_fetch_keeps_the_previous_cache(store):
    refresh(HolidayClient(fetch=Fetch()), store, date(2026, 10, 15))

    refresh(HolidayClient(fetch=Fetch(broken={2026})), store, date(2026, 10, 16))

    assert store.get(date(2026, 1, 1)).name == "Año nuevo"


def test_an_empty_answer_keeps_the_previous_cache(store):
    refresh(HolidayClient(fetch=Fetch()), store, date(2026, 10, 15))

    refresh(HolidayClient(fetch=Fetch({2026: []})), store, date(2026, 10, 16))

    assert store.get(date(2026, 1, 1)) is not None


def test_one_year_failing_does_not_stop_the_other(store):
    refresh(HolidayClient(fetch=Fetch(broken={2026})), store, date(2026, 12, 1))

    assert store.get(date(2027, 1, 1)) is not None


def test_without_ever_having_data_there_is_no_holiday(store):
    refresh(HolidayClient(fetch=Fetch(broken={2026})), store, date(2026, 10, 15))

    assert store.get(date(2026, 1, 1)) is None


# --- el nombre dicho ---

# Los nombres de 2026 como los devolvió la API, ya sin el paréntesis de la fecha.
REAL_2026 = (
    "Año nuevo",
    "Carnaval",
    "Puente turístico no laborable",
    "Día Nacional de la Memoria por la Verdad y la Justicia",
    "Día del Veterano y de los Caídos en la Guerra de Malvinas",
    "Viernes Santo",
    "Día del Trabajador",
    "Día de la Revolución de Mayo",
    "Paso a la Inmortalidad del General Martín Güemes",
    "Paso a la Inmortalidad del General Manuel Belgrano",
    "Día de la Independencia",
    "Paso a la Inmortalidad del Gral. José de San Martín",
    "Día del Respeto a la Diversidad Cultural",
    "Visita del papa León XIV",
    "Día de la Soberanía Nacional",
    "Día de la Inmaculada Concepción de María",
    "Navidad",
)
CHANGED_2026 = {
    "Paso a la Inmortalidad del Gral. José de San Martín":
        "Paso a la Inmortalidad del General José de San Martín",
    "Visita del papa León XIV": "Visita del papa León catorce",
}


@pytest.mark.parametrize("name", REAL_2026)
def test_the_real_names_of_2026_are_said_well(name):
    assert spoken_name(name) == CHANGED_2026.get(name, name)


def test_the_pope_is_said_in_words_and_written_as_published():
    holiday = Holiday(date(2026, 11, 9), FIXED, "Visita del papa León XIV")

    assert holiday.spoken == "Hoy es feriado: Visita del papa León catorce."
    assert holiday.written == "Hoy es feriado: Visita del papa León XIV."


def test_the_general_is_said_whole_and_written_as_published():
    holiday = Holiday(date(2026, 8, 17), MOVABLE, "Paso a la Inmortalidad del Gral. José de San Martín")

    assert "del General José" in holiday.spoken
    assert "Gral." in holiday.written


@pytest.mark.parametrize(
    ("abbreviation", "word"),
    [("Gral.", "General"), ("Dr.", "Doctor"), ("Sta.", "Santa"), ("Sto.", "Santo")],
)
def test_the_short_abbreviations_are_said_whole(abbreviation, word):
    assert spoken_name(f"Día de {abbreviation} Pérez") == f"Día de {word} Pérez"


@pytest.mark.parametrize(
    ("roman", "words"),
    [("I", "uno"), ("IV", "cuatro"), ("IX", "nueve"), ("XIV", "catorce"),
     ("XXIII", "veintitrés"), ("XXXIX", "treinta y nueve"), ("XL", "cuarenta")],
)
def test_a_roman_numeral_after_a_proper_name_is_said_in_words(roman, words):
    assert spoken_name(f"Visita de Juan {roman}") == f"Visita de Juan {words}"


@pytest.mark.parametrize(
    "name",
    [
        "I Congreso Nacional",
        "V Centenario",
        "Día de la CGT",
        "Feria del libro X",
        "Visita de Juan IIII",
        "Visita de Juan VX",
    ],
)
def test_what_only_looks_roman_is_left_alone(name):
    assert spoken_name(name) == name

"""El versículo del día, en la Nueva Traducción Viviente."""

from datetime import date

from homeauto.bible import VerseOfTheDay

TODAY = date(2026, 9, 23)  # día doscientos sesenta y seis del año

VOTD = {
    "votd": [
        {"day": 265, "usfm": ["JHN.3.16"], "image_id": 1},
        {"day": 266, "usfm": ["PSA.19.14"], "image_id": 2},
    ]
}

VERSES = {
    "PSA.19.14": {
        "reference": {"usfm": ["PSA.19.14"], "human": "Salmos 19:14", "version_id": 127},
        "content": "Que las palabras de mi boca\ny la meditación de mi corazón\n"
        "sean de tu agrado,\noh SEÑOR, mi roca y mi redentor.",
    },
    "ISA.43.18": {
        "reference": {"usfm": ["ISA.43.18"], "human": "Isaías 43:18"},
        "content": "Pero olvida todo eso;\nno es nada comparado con lo que voy a hacer.",
    },
    "ISA.43.19": {
        "reference": {"usfm": ["ISA.43.19"], "human": "Isaías 43:19"},
        "content": "Pues estoy por hacer algo nuevo.",
    },
    "1JN.4.8": {
        "reference": {"usfm": ["1JN.4.8"], "human": "1 Juan 4:8"},
        "content": "pero el que no ama no conoce a Dios, porque Dios es amor.",
    },
    "2KI.1.1": {
        "reference": {"usfm": ["2KI.1.1"], "human": "2 Reyes 1:1"},
        "content": "Después de la muerte de Acab, la tierra de Moab se rebeló.",
    },
    "NUM.1.46": {
        "reference": {"usfm": ["NUM.1.46"], "human": "Números 1:46"},
        "content": "El total fue de 603.550.",
    },
}


def fetcher(votd=VOTD, verses=VERSES, calls=None):
    """Un doble por URL: la lista del año o un versículo por su referencia."""
    def fetch(url):
        if calls is not None:
            calls.append(url)
        if "votd" in url:
            if isinstance(votd, Exception):
                raise votd
            return votd
        for usfm, payload in verses.items():
            if f"reference={usfm}" in url:
                return payload
        raise AssertionError(f"nadie pidió {url}")

    return fetch


def of_the_day(*usfm, **kwargs):
    votd = {"votd": [{"day": 266, "usfm": list(usfm), "image_id": 1}]}
    return VerseOfTheDay(fetch=fetcher(votd=votd, **kwargs), today=lambda: TODAY)


def test_the_verse_of_today_is_the_one_of_this_day_of_the_year():
    passage = VerseOfTheDay(fetch=fetcher(), today=lambda: TODAY).passage()

    assert "mi roca y mi redentor" in passage.spoken
    assert "Salmos 19:14" in passage.written


def test_it_is_asked_in_the_nueva_traduccion_viviente():
    calls = []
    VerseOfTheDay(fetch=fetcher(calls=calls), today=lambda: TODAY).passage()

    verse_calls = [url for url in calls if "reference=" in url]
    assert verse_calls and all("id=127" in url for url in verse_calls)


def test_the_reference_is_said_in_words():
    said = of_the_day("PSA.19.14").passage().spoken

    assert said.startswith("El versículo del día, de Salmos, capítulo diecinueve, versículo catorce:")


def test_the_verse_text_is_said_as_written_in_one_line():
    said = of_the_day("PSA.19.14").passage().spoken

    assert "Que las palabras de mi boca y la meditación de mi corazón" in said
    assert "\n" not in said


def test_a_word_in_capitals_is_said_as_a_word():
    """SEÑOR en mayúsculas se deletrearía. Se baja la caja, no se toca la palabra."""
    said = of_the_day("PSA.19.14").passage().spoken

    assert "oh Señor," in said


def test_the_chat_keeps_the_verse_as_published():
    written = of_the_day("PSA.19.14").passage().written

    assert written.startswith("📖 Salmos 19:14 (NTV)")
    assert "oh SEÑOR" in written


def test_several_verses_are_said_as_a_range():
    passage = of_the_day("ISA.43.18", "ISA.43.19").passage()

    assert "de Isaías, capítulo cuarenta y tres, versículos dieciocho al diecinueve:" in passage.spoken
    assert "comparado con lo que voy a hacer. Pues estoy por hacer algo nuevo." in passage.spoken
    assert "Isaías 43:18-19" in passage.written


def test_a_numbered_letter_is_said_with_its_ordinal():
    said = of_the_day("1JN.4.8").passage().spoken

    assert "de Primera de Juan, capítulo cuatro, versículo ocho:" in said


def test_a_numbered_book_is_said_with_its_ordinal():
    said = of_the_day("2KI.1.1").passage().spoken

    assert "de Segundo de Reyes, capítulo uno, versículo uno:" in said


def test_nothing_spoken_carries_a_digit():
    for usfm in ("PSA.19.14", "1JN.4.8", "2KI.1.1"):
        said = of_the_day(usfm).passage().spoken
        assert not any(character.isdigit() for character in said), said


def test_a_verse_with_a_digit_is_only_written():
    passage = of_the_day("NUM.1.46").passage()

    assert passage.spoken == ""
    assert "603.550" in passage.written


def test_a_day_without_a_verse_has_nothing():
    votd = {"votd": [{"day": 1, "usfm": ["JHN.3.16"], "image_id": 1}]}

    assert VerseOfTheDay(fetch=fetcher(votd=votd), today=lambda: TODAY).passage() is None


def test_a_verse_that_comes_back_empty_has_nothing():
    verses = {"PSA.19.14": {"reference": {"human": "Salmos 19:14"}, "content": "  "}}

    assert of_the_day("PSA.19.14", verses=verses).passage() is None

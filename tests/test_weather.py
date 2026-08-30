import pytest

from homeauto.weather import WeatherError, WeatherClient, describe_code

PAYLOAD = {
    "current": {
        "temperature_2m": 14.4,
        "apparent_temperature": 12.1,
        "relative_humidity_2m": 71,
        "weather_code": 3,
        "wind_speed_10m": 18.5,
    },
    "daily": {
        "temperature_2m_max": [22.3],
        "temperature_2m_min": [10.8],
        "precipitation_probability_max": [20],
        "weather_code": [61],
    },
}


def client(payload=None, boom=None):
    def fetch(latitude, longitude):
        if boom:
            raise boom
        return payload if payload is not None else PAYLOAD

    return WeatherClient(latitude=-34.6, longitude=-58.4, place="casa", fetch=fetch)


def test_reads_the_current_conditions():
    forecast = client().now()

    assert forecast.temperature == 14
    assert forecast.feels_like == 12
    assert forecast.humidity == 71
    assert forecast.maximum == 22
    assert forecast.minimum == 11
    assert forecast.rain_chance == 20


def test_temperatures_are_rounded_for_speech():
    """Nadie dice 'catorce coma cuatro grados'."""
    forecast = client().now()

    assert isinstance(forecast.temperature, int)
    assert isinstance(forecast.maximum, int)


def test_describes_the_sky_in_words():
    assert "nublado" in describe_code(3).lower()
    assert "despejado" in describe_code(0).lower()
    assert "lluvia" in describe_code(61).lower()
    assert "niebla" in describe_code(45).lower()
    assert "tormenta" in describe_code(95).lower()


def test_an_unknown_code_does_not_explode():
    assert describe_code(999)


def test_the_spoken_text_reads_like_a_person():
    spoken = client().spoken()

    assert "14" in spoken
    assert "grados" in spoken
    assert spoken.endswith(".")
    assert "None" not in spoken


def test_the_spoken_text_names_the_place():
    assert "casa" in client().spoken()


def test_it_mentions_rain_when_it_is_likely():
    payload = {**PAYLOAD, "daily": {**PAYLOAD["daily"], "precipitation_probability_max": [80]}}

    assert "80" in client(payload).spoken()


def test_it_does_not_nag_about_rain_when_there_is_none():
    payload = {**PAYLOAD, "daily": {**PAYLOAD["daily"], "precipitation_probability_max": [0]}}

    assert "lluvia" not in client(payload).spoken().lower()


def test_it_warns_when_it_feels_much_colder():
    payload = {**PAYLOAD, "current": {**PAYLOAD["current"], "apparent_temperature": 5.0}}

    spoken = client(payload).spoken()

    assert "sensación" in spoken.lower() or "se sienten" in spoken.lower()


def test_a_network_failure_is_reported_in_spanish():
    with pytest.raises(WeatherError, match="No pude"):
        client(boom=TimeoutError("se cayó")).now()


def test_a_broken_answer_is_reported():
    with pytest.raises(WeatherError):
        client(payload={"current": {}}).now()


def test_missing_daily_block_is_reported():
    with pytest.raises(WeatherError):
        client(payload={"current": PAYLOAD["current"]}).now()

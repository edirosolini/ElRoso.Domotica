"""Aviso de lluvia: mirar el pronóstico por hora y avisar una vez."""

from datetime import datetime

import pytest

from homeauto.watch.marks import Marks
from homeauto.weather import RainWatcher, WeatherClient, WeatherError

NOW = datetime(2026, 8, 31, 10, 0)


def payload(hours):
    """Open-Meteo devuelve dos listas paralelas: la hora y su probabilidad."""
    return {
        "current": {
            "temperature_2m": 20,
            "apparent_temperature": 20,
            "relative_humidity_2m": 50,
            "weather_code": 0,
        },
        "daily": {
            "temperature_2m_max": [25],
            "temperature_2m_min": [12],
            "precipitation_probability_max": [80],
            "weather_code": [0],
        },
        "hourly": {
            "time": [moment for moment, _ in hours],
            "precipitation_probability": [chance for _, chance in hours],
        },
    }


def client(hours):
    return WeatherClient(latitude=-34.6, longitude=-58.4, fetch=lambda lat, lon: payload(hours))


def test_rain_ahead_finds_the_first_likely_hour():
    weather = client([
        ("2026-08-31T10:00", 0),
        ("2026-08-31T11:00", 10),
        ("2026-08-31T13:00", 80),
        ("2026-08-31T14:00", 90),
    ])

    rain = weather.rain_ahead(NOW, hours=6)

    assert rain.when == datetime(2026, 8, 31, 13, 0)
    assert rain.chance == 80


def test_rain_that_is_only_a_maybe_is_not_worth_a_warning():
    weather = client([("2026-08-31T12:00", 30), ("2026-08-31T13:00", 45)])

    assert weather.rain_ahead(NOW, hours=6) is None


def test_rain_past_the_window_is_not_announced_yet():
    weather = client([("2026-08-31T20:00", 90)])

    assert weather.rain_ahead(NOW, hours=6) is None


def test_an_hour_already_gone_does_not_count():
    weather = client([("2026-08-31T08:00", 90)])

    assert weather.rain_ahead(NOW, hours=6) is None


def test_an_aware_clock_still_matches_the_local_hours():
    """El pronóstico viene en hora local y sin offset; el reloj puede traerlo."""
    from datetime import timedelta, timezone

    weather = client([("2026-08-31T13:00", 80)])
    aware = NOW.replace(tzinfo=timezone(timedelta(hours=-3)))

    assert weather.rain_ahead(aware, hours=6).when == datetime(2026, 8, 31, 13, 0)


def test_a_forecast_without_hours_is_not_an_error():
    weather = WeatherClient(latitude=-34.6, longitude=-58.4, fetch=lambda lat, lon: {"current": {}})

    assert weather.rain_ahead(NOW, hours=6) is None


# --- el watcher ------------------------------------------------------------


class FakeWeather:
    def __init__(self, rain=None, fail=False):
        self.rain = rain
        self.fail = fail
        self.calls = 0

    def rain_ahead(self, now, hours):
        self.calls += 1
        if self.fail:
            raise WeatherError("no contesta")
        return self.rain


class Rain:
    def __init__(self, when, chance):
        self.when = when
        self.chance = chance


@pytest.fixture
def watcher(tmp_path):
    def build(weather, clock=lambda: NOW):
        said = []
        return (
            RainWatcher(
                weather=weather,
                announce=said.append,
                marks=Marks(tmp_path / "jobs.db"),
                clock=clock,
            ),
            said,
        )

    return build


def test_it_announces_the_rain_in_words(watcher):
    watch, said = watcher(FakeWeather(Rain(datetime(2026, 8, 31, 15, 0), 80)))

    watch.check()

    assert said == ["Ojo, va a llover a eso de las tres de la tarde."]


def test_it_does_not_announce_the_same_day_twice(watcher):
    watch, said = watcher(FakeWeather(Rain(datetime(2026, 8, 31, 15, 0), 80)))

    watch.check()
    watch.check()

    assert len(said) == 1


def test_the_next_day_it_warns_again(tmp_path, watcher):
    weather = FakeWeather(Rain(datetime(2026, 8, 31, 15, 0), 80))
    today = datetime(2026, 8, 31, 10, 0)
    tomorrow = datetime(2026, 9, 1, 10, 0)
    moment = [today]
    watch, said = watcher(weather, clock=lambda: moment[0])

    watch.check()
    moment[0] = tomorrow
    watch.check()

    assert len(said) == 2


def test_nothing_is_said_when_no_rain_is_coming(watcher):
    watch, said = watcher(FakeWeather(None))

    watch.check()

    assert said == []


def test_a_forecast_that_fails_stays_quiet_and_retries(watcher):
    weather = FakeWeather(fail=True)
    watch, said = watcher(weather)

    watch.check()
    watch.check()

    assert said == []
    assert weather.calls == 2


def test_an_announcement_that_fails_is_not_marked_as_done(tmp_path):
    """Igual que en la agenda: lo que no se dijo se reintenta."""
    weather = FakeWeather(Rain(datetime(2026, 8, 31, 15, 0), 80))
    attempts = []

    def announce(text):
        attempts.append(text)
        raise RuntimeError("el parlante no está")

    watch = RainWatcher(
        weather=weather,
        announce=announce,
        marks=Marks(tmp_path / "jobs.db"),
        clock=lambda: NOW,
    )

    watch.check()
    watch.check()

    assert len(attempts) == 2


def test_the_warning_carries_no_digits(watcher):
    watch, said = watcher(FakeWeather(Rain(datetime(2026, 8, 31, 21, 30), 90)))

    watch.check()

    assert not any(char.isdigit() for char in said[0])

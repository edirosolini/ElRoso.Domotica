"""Los otros avisos del cielo: calor, frío, viento y tormenta.

Uno por día cada uno, con su propia marca: el que avisa de calor no puede
quedarse con el turno del que avisa de viento.
"""

from datetime import datetime

import pytest

from homeauto.watch.marks import Marks
from homeauto.weather import WeatherClient, WeatherWatcher

NOW = datetime(2026, 8, 31, 8, 0)


def payload(maximum=25, minimum=12, hours=()):
    return {
        "current": {
            "temperature_2m": 20,
            "apparent_temperature": 20,
            "relative_humidity_2m": 50,
            "weather_code": 0,
        },
        "daily": {
            "temperature_2m_max": [maximum],
            "temperature_2m_min": [minimum],
            "precipitation_probability_max": [10],
            "weather_code": [0],
        },
        "hourly": {
            "time": [hour[0] for hour in hours],
            "precipitation_probability": [0 for _ in hours],
            "wind_gusts_10m": [hour[1] for hour in hours],
            "weather_code": [hour[2] for hour in hours],
        },
    }


def watcher(tmp_path, said, now=NOW, **kwargs):
    weather = WeatherClient(
        latitude=-34.6, longitude=-58.4, fetch=lambda lat, lon: payload(**kwargs)
    )
    return WeatherWatcher(
        weather=weather,
        announce=said.append,
        marks=Marks(tmp_path / "jobs.db"),
        clock=lambda: now,
    )


def test_a_hot_day_is_announced_in_words(tmp_path):
    said = []

    watcher(tmp_path, said, maximum=34).check()

    assert said and "treinta y cuatro grados" in said[0]
    assert not any(character.isdigit() for character in said[0])


def test_a_normal_day_says_nothing(tmp_path):
    said = []

    watcher(tmp_path, said, maximum=28, minimum=14).check()

    assert said == []


def test_a_freezing_night_is_announced(tmp_path):
    said = []

    watcher(tmp_path, said, minimum=2).check()

    assert said and "dos grados" in said[0]


def test_below_zero_is_said_as_below_zero(tmp_path):
    said = []

    watcher(tmp_path, said, minimum=-3).check()

    assert "menos tres grados" in said[0]


def test_heat_and_cold_wait_for_a_civilised_hour(tmp_path):
    """A las cuatro de la mañana nadie necesita saber la máxima de hoy."""
    said = []

    watcher(tmp_path, said, now=datetime(2026, 8, 31, 4, 0), maximum=36).check()

    assert said == []


def test_a_strong_gust_is_announced_with_its_hour(tmp_path):
    said = []

    watcher(
        tmp_path,
        said,
        hours=[("2026-08-31T09:00", 20, 0), ("2026-08-31T12:00", 65, 0)],
    ).check()

    assert said and "mediodía" in said[0]
    assert "sesenta y cinco" in said[0]


def test_a_breeze_is_not_a_warning(tmp_path):
    said = []

    watcher(tmp_path, said, hours=[("2026-08-31T12:00", 30, 0)]).check()

    assert said == []


def test_a_storm_ahead_is_announced(tmp_path):
    said = []

    watcher(tmp_path, said, hours=[("2026-08-31T13:00", 10, 95)]).check()

    assert said and "tormenta" in said[0].lower()


def test_what_is_past_the_window_is_not_ahead(tmp_path):
    said = []

    watcher(tmp_path, said, hours=[("2026-08-31T23:00", 80, 95)]).check()

    assert said == []


def test_each_warning_is_said_once_a_day(tmp_path):
    said = []
    watch = watcher(tmp_path, said, maximum=35)

    watch.check()
    watch.check()

    assert len(said) == 1


def test_a_warning_that_could_not_be_said_is_retried(tmp_path):
    """Igual que la lluvia y la agenda: lo que no salió no se marca como hecho."""
    attempts = []

    def failing(text):
        attempts.append(text)
        raise RuntimeError("el parlante no contesta")

    weather = WeatherClient(
        latitude=-34.6, longitude=-58.4, fetch=lambda lat, lon: payload(maximum=35)
    )
    watch = WeatherWatcher(
        weather=weather,
        announce=failing,
        marks=Marks(tmp_path / "jobs.db"),
        clock=lambda: NOW,
    )

    watch.check()
    watch.check()

    assert len(attempts) == 2


def test_two_different_warnings_do_not_share_a_turn(tmp_path):
    said = []

    watcher(
        tmp_path,
        said,
        maximum=35,
        hours=[("2026-08-31T12:00", 70, 0)],
    ).check()

    assert len(said) == 2, "el calor y el viento son dos avisos distintos"


def test_a_forecast_that_fails_is_not_an_alert(tmp_path):
    def broken(lat, lon):
        raise RuntimeError("open-meteo no contesta")

    watch = WeatherWatcher(
        weather=WeatherClient(latitude=-34.6, longitude=-58.4, fetch=broken),
        announce=lambda text: pytest.fail("no hay nada que avisar"),
        marks=Marks(tmp_path / "jobs.db"),
        clock=lambda: NOW,
    )

    assert watch.check() == []

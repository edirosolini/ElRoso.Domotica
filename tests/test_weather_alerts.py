"""Los otros avisos del cielo: calor, frío, ultravioleta, aire, viento y tormenta.

Uno por día cada uno, con su propia marca, y todos los de una vuelta en un solo anuncio.
"""

from datetime import datetime

import pytest

from homeauto.watch.marks import Marks
from homeauto.air import AirError
from homeauto.weather import (
    AIR_MARK,
    COLD_MARK,
    HEAT_MARK,
    SKY_ALERTS,
    STORM_MARK,
    UV_MARK,
    WIND_MARK,
    WeatherClient,
    WeatherWatcher,
)

NOW = datetime(2026, 8, 31, 8, 0)


def payload(maximum=25, minimum=12, hours=(), uv=None):
    daily_uv = {} if uv is None else {"uv_index_max": [uv]}
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
            **daily_uv,
        },
        "hourly": {
            "time": [hour[0] for hour in hours],
            "precipitation_probability": [0 for _ in hours],
            "wind_gusts_10m": [hour[1] for hour in hours],
            "weather_code": [hour[2] for hour in hours],
        },
    }


def watcher(tmp_path, said, now=NOW, air=None, **kwargs):
    weather = WeatherClient(
        latitude=-34.6, longitude=-58.4, fetch=lambda lat, lon: payload(**kwargs)
    )
    return WeatherWatcher(
        weather=weather,
        announce=said.append,
        marks=Marks(tmp_path / "jobs.db"),
        clock=lambda: now,
        air=air,
    )


class FakeAir:
    """Un AirClient que contesta un índice fijo y cuenta las consultas."""

    def __init__(self, worst=None, boom=None):
        self.worst = worst
        self.boom = boom
        self.asked = 0

    def worst_today(self, now):
        self.asked += 1
        if self.boom:
            raise self.boom
        return self.worst


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


def test_two_different_warnings_go_out_in_one_announcement(tmp_path):
    said = []

    watcher(
        tmp_path,
        said,
        maximum=35,
        hours=[("2026-08-31T12:00", 70, 0)],
    ).check()

    assert len(said) == 1
    assert "treinta y cinco grados" in said[0]
    assert "setenta kilómetros por hora" in said[0]


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


def test_an_extreme_uv_is_announced_in_words(tmp_path):
    said = []

    watcher(tmp_path, said, uv=11.2).check()

    assert said == [
        "Ojo con el sol: hoy el índice ultravioleta llega a once, extremo."
    ]


def test_a_uv_below_extreme_says_nothing(tmp_path):
    said = []

    watcher(tmp_path, said, uv=10.4).check()

    assert said == []


def test_the_uv_waits_for_a_civilised_hour(tmp_path):
    said = []

    watcher(tmp_path, said, now=datetime(2026, 8, 31, 12, 0), uv=12).check()

    assert said == []


def test_the_uv_is_said_once_a_day(tmp_path):
    said = []
    watch = watcher(tmp_path, said, uv=12)

    watch.check()
    watch.check()

    assert len(said) == 1


def test_bad_air_is_announced_without_a_figure(tmp_path):
    said = []

    watcher(tmp_path, said, air=FakeAir(worst=101)).check()

    assert said == [
        "Ojo con el aire: hoy se espera mala calidad del aire, mejor ventilar poco."
    ]


def test_acceptable_air_says_nothing(tmp_path):
    said = []

    watcher(tmp_path, said, air=FakeAir(worst=100)).check()

    assert said == []


def test_an_air_without_data_says_nothing(tmp_path):
    said = []

    watcher(tmp_path, said, air=FakeAir(worst=None)).check()

    assert said == []


def test_the_air_waits_for_a_civilised_hour(tmp_path):
    said = []
    air = FakeAir(worst=180)

    watcher(tmp_path, said, now=datetime(2026, 8, 31, 4, 0), air=air).check()

    assert said == []
    assert air.asked == 0


def test_the_air_is_not_asked_again_once_said_today(tmp_path):
    said = []
    air = FakeAir(worst=180)
    watch = watcher(tmp_path, said, air=air)

    watch.check()
    watch.check()

    assert len(said) == 1
    assert air.asked == 1


def test_an_air_that_fails_does_not_cost_the_uv(tmp_path):
    said = []

    watcher(tmp_path, said, uv=12, air=FakeAir(boom=AirError("sin red"))).check()

    assert len(said) == 1
    assert "ultravioleta" in said[0]


def test_uv_air_and_heat_are_one_announcement_with_three_marks(tmp_path):
    said = []
    marks = Marks(tmp_path / "jobs.db")

    watcher(tmp_path, said, maximum=35, uv=12, air=FakeAir(worst=150)).check()

    assert len(said) == 1
    assert all(marks.get(mark) == NOW for mark in (HEAT_MARK, UV_MARK, AIR_MARK))


def test_an_air_warning_that_could_not_be_said_is_retried(tmp_path):
    attempts = []

    def failing(text):
        attempts.append(text)
        raise RuntimeError("el parlante no contesta")

    weather = WeatherClient(latitude=-34.6, longitude=-58.4, fetch=lambda lat, lon: payload())
    watch = WeatherWatcher(
        weather=weather,
        announce=failing,
        marks=Marks(tmp_path / "jobs.db"),
        clock=lambda: NOW,
        air=FakeAir(worst=150),
    )

    watch.check()
    watch.check()

    assert len(attempts) == 2


def test_no_digit_reaches_the_synthesizer_from_uv_or_air(tmp_path):
    said = []

    watcher(tmp_path, said, uv=13.7, air=FakeAir(worst=212)).check()

    assert len(said) == 1
    assert not any(character.isdigit() for text in said for character in text)


def test_uv_and_air_are_polished_once_together(tmp_path):
    seen = []

    def polish(text, must_keep=()):
        seen.append(text)
        return text.upper()

    said = []
    WeatherWatcher(
        weather=WeatherClient(
            latitude=-34.6, longitude=-58.4, fetch=lambda lat, lon: payload(uv=12)
        ),
        announce=said.append,
        marks=Marks(tmp_path / "jobs.db"),
        clock=lambda: NOW,
        polish=polish,
        air=FakeAir(worst=150),
    ).check()

    assert len(seen) == 1
    assert said == [seen[0].upper()]


def counting_watcher(tmp_path, calls, alerts=SKY_ALERTS, air=None, said=None, **kwargs):
    def fetch(lat, lon):
        calls.append((lat, lon))
        return payload(**kwargs)

    return WeatherWatcher(
        weather=WeatherClient(latitude=-34.6, longitude=-58.4, fetch=fetch),
        announce=(lambda text: None) if said is None else said.append,
        marks=Marks(tmp_path / "jobs.db"),
        clock=lambda: NOW,
        air=air,
        alerts=alerts,
    )


def test_heat_cold_and_uv_share_one_daily_request(tmp_path):
    calls = []

    said = counting_watcher(tmp_path, calls, maximum=35, minimum=2, uv=12).check()

    assert len(said) == 1
    assert len(calls) == 2, "un pedido para el día y otro para las próximas horas"


def test_the_day_is_not_asked_once_heat_cold_and_uv_are_marked(tmp_path):
    calls = []
    marks = Marks(tmp_path / "jobs.db")
    for mark in (HEAT_MARK, COLD_MARK, UV_MARK):
        marks.set(mark, NOW)

    counting_watcher(tmp_path, calls, maximum=35, minimum=2, uv=12).check()

    assert len(calls) == 1, "solo el pedido de las próximas horas"


# --- un solo anuncio por vuelta ----------------------------------------------

GUST = [("2026-08-31T12:00", 70, 0)]


def test_heat_and_uv_in_one_round_are_one_announcement_and_two_marks(tmp_path):
    said = []
    marks = Marks(tmp_path / "jobs.db")

    watcher(tmp_path, said, maximum=35, uv=12).check()

    assert len(said) == 1
    assert "treinta y cinco grados" in said[0]
    assert "ultravioleta" in said[0]
    assert marks.get(HEAT_MARK) == NOW
    assert marks.get(UV_MARK) == NOW


def test_an_announcement_that_fails_leaves_no_mark_and_is_retried_whole(tmp_path):
    attempts = []

    def failing(text):
        attempts.append(text)
        raise RuntimeError("el parlante no contesta")

    marks = Marks(tmp_path / "jobs.db")
    watch = WeatherWatcher(
        weather=WeatherClient(
            latitude=-34.6, longitude=-58.4,
            fetch=lambda lat, lon: payload(maximum=35, hours=GUST),
        ),
        announce=failing,
        marks=marks,
        clock=lambda: NOW,
    )

    assert watch.check() == []
    watch.check()

    assert marks.get(HEAT_MARK) is None
    assert marks.get(WIND_MARK) is None
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]


def test_with_the_heat_already_said_only_the_wind_goes_out(tmp_path):
    said = []
    Marks(tmp_path / "jobs.db").set(HEAT_MARK, NOW)

    watcher(tmp_path, said, maximum=35, hours=GUST).check()

    assert said == [
        "Ojo, se viene viento a eso de las doce del mediodía, "
        "con ráfagas de setenta kilómetros por hora."
    ]


def test_a_single_warning_keeps_its_own_phrase(tmp_path):
    said = []

    watcher(tmp_path, said, maximum=35).check()

    assert said == ["Ojo con el calor: hoy la máxima es de treinta y cinco grados."]


def test_a_single_warning_is_polished_as_before(tmp_path):
    seen = []

    def polish(text, must_keep=()):
        seen.append((text, tuple(must_keep)))
        return text

    WeatherWatcher(
        weather=WeatherClient(
            latitude=-34.6, longitude=-58.4, fetch=lambda lat, lon: payload(maximum=35)
        ),
        announce=lambda text: None,
        marks=Marks(tmp_path / "jobs.db"),
        clock=lambda: NOW,
        polish=polish,
    ).check()

    assert seen == [("Ojo con el calor: hoy la máxima es de treinta y cinco grados.", ())]


def test_the_combined_text_has_no_digits_and_is_polished_once_keeping_each_piece(tmp_path):
    seen = []

    def polish(text, must_keep=()):
        seen.append((text, tuple(must_keep)))
        return text

    said = []
    WeatherWatcher(
        weather=WeatherClient(
            latitude=-34.6, longitude=-58.4,
            fetch=lambda lat, lon: payload(
                maximum=35, uv=12, hours=[("2026-08-31T12:00", 70, 95)]
            ),
        ),
        announce=said.append,
        marks=Marks(tmp_path / "jobs.db"),
        clock=lambda: NOW,
        polish=polish,
        air=FakeAir(worst=150),
    ).check()

    assert len(seen) == 1
    text, keep = seen[0]
    assert said == [text]
    assert not any(character.isdigit() for character in text)
    for term in ("treinta y cinco", "doce", "aire", "setenta", "las doce del mediodía", "tormenta"):
        assert term in keep
        assert term in text
    for mark in (HEAT_MARK, UV_MARK, AIR_MARK, WIND_MARK, STORM_MARK):
        assert Marks(tmp_path / "jobs.db").get(mark) == NOW


# --- avisos apagados ----------------------------------------------------------


def without(*names):
    return tuple(name for name in SKY_ALERTS if name not in names)


def test_the_heat_turned_off_is_not_said(tmp_path):
    said = []
    calls = []

    counting_watcher(
        tmp_path, calls, alerts=without("heat"), said=said, maximum=35, uv=12
    ).check()

    assert len(said) == 1
    assert "calor" not in said[0] and "treinta y cinco" not in said[0]
    assert "ultravioleta" in said[0]


def test_the_cold_turned_off_is_not_said(tmp_path):
    said = []

    counting_watcher(tmp_path, [], alerts=without("cold"), said=said, minimum=1).check()

    assert said == []


def test_the_uv_turned_off_is_not_said(tmp_path):
    said = []

    counting_watcher(tmp_path, [], alerts=without("uv"), said=said, uv=12).check()

    assert said == []


def test_without_heat_cold_and_uv_the_day_is_not_asked(tmp_path):
    calls = []

    counting_watcher(
        tmp_path, calls, alerts=without("heat", "cold", "uv"), maximum=35, minimum=1, uv=12
    ).check()

    assert len(calls) == 1, "solo el pedido de las próximas horas"


def test_the_air_turned_off_is_not_asked(tmp_path):
    said = []
    air = FakeAir(worst=180)

    counting_watcher(tmp_path, [], alerts=without("air"), air=air, said=said).check()

    assert said == []
    assert air.asked == 0


def test_the_wind_turned_off_is_not_said(tmp_path):
    said = []

    counting_watcher(tmp_path, [], alerts=without("wind"), said=said, hours=GUST).check()

    assert said == []


def test_the_storm_turned_off_is_not_said(tmp_path):
    said = []

    counting_watcher(
        tmp_path, [], alerts=without("storm"), said=said, hours=[("2026-08-31T13:00", 10, 95)]
    ).check()

    assert said == []


def test_without_wind_and_storm_the_hours_are_not_asked(tmp_path):
    calls = []

    counting_watcher(
        tmp_path, calls, alerts=without("wind", "storm"), hours=GUST
    ).check()

    assert len(calls) == 1, "solo el pedido del día"


def test_with_everything_off_nothing_is_asked(tmp_path):
    calls = []
    air = FakeAir(worst=180)

    counting_watcher(tmp_path, calls, alerts=(), air=air, maximum=35, hours=GUST).check()

    assert calls == []
    assert air.asked == 0

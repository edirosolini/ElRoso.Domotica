"""La calidad del aire de hoy, por Open-Meteo."""

from datetime import datetime

import pytest

from homeauto.air import AirClient, AirError, fetch_air_quality

NOW = datetime(2026, 10, 15, 8, 0)


def hourly(values, day="2026-10-15"):
    return {
        "hourly": {
            "time": [f"{day}T{hour:02d}:00" for hour in range(len(values))],
            "us_aqi": list(values),
            "pm2_5": [10.0 for _ in values],
        }
    }


def client(payload=None, boom=None):
    def fetch(latitude, longitude):
        if boom:
            raise boom
        return payload

    return AirClient(-34.6, -58.4, fetch=fetch)


def test_the_worst_hour_between_eight_and_eight_is_the_one_that_counts():
    values = [300] * 8 + [40, 55, 120, 60] + [50] * 9 + [400] * 3

    assert client(hourly(values)).worst_today(NOW) == 120


def test_missing_hours_are_ignored():
    values = [None] * 8 + [None, 70, None] + [None] * 13

    assert client(hourly(values)).worst_today(NOW) == 70


def test_another_day_is_not_today():
    values = [200] * 24

    assert client(hourly(values, day="2026-10-16")).worst_today(NOW) is None


def test_a_clock_with_a_zone_is_compared_as_local():
    values = [10] * 8 + [150] + [10] * 15
    zoned = datetime.fromisoformat("2026-10-15T08:00-03:00")

    assert client(hourly(values)).worst_today(zoned) == 150


def test_a_broken_answer_is_an_air_error():
    with pytest.raises(AirError):
        client({"nada": 1}).worst_today(NOW)


def test_a_failed_request_is_an_air_error():
    with pytest.raises(AirError):
        client(boom=RuntimeError("sin red")).worst_today(NOW)


def test_the_request_asks_for_today_in_local_time():
    asked = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def get(url, params, timeout):
        asked["url"] = url
        asked.update(params)
        return Response()

    assert fetch_air_quality(-34.6, -58.4, get=get) == {"ok": True}
    assert asked["url"] == "https://air-quality-api.open-meteo.com/v1/air-quality"
    assert asked["hourly"] == "us_aqi,pm2_5"
    assert asked["timezone"] == "auto"
    assert asked["forecast_days"] == 1

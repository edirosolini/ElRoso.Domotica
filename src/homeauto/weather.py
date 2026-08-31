"""Weather, read out loud.

Uses Open-Meteo: free, no account, no API key. Nothing here depends on the
Google Assistant, which is what fails when you ask the speaker directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from homeauto.verbalize import clock as spoken_clock, number
from homeauto.polish import as_is

log = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 15

# WMO weather codes, in the words a person would use out loud.
SKY = {
    (0,): "despejado",
    (1, 2): "parcialmente nublado",
    (3,): "nublado",
    (45, 48): "con niebla",
    (51, 53, 55, 56, 57): "con llovizna",
    (61, 63, 65, 66, 67, 80, 81, 82): "con lluvia",
    (71, 73, 75, 77, 85, 86): "con nieve",
    (95, 96, 99): "con tormenta",
}

# Below this gap, saying the "feels like" adds nothing.
FEELS_LIKE_GAP = 3
RAIN_WORTH_MENTIONING = 20

# How far ahead the rain warning looks, and how sure it has to be. Warning
# about a coin flip is how a warning stops being read.
RAIN_WINDOW_HOURS = 6
RAIN_ALERT_CHANCE = 60
RAIN_MARK = "rain-alert"


class WeatherError(Exception):
    """The forecast could not be fetched or understood."""


def describe_code(code: int) -> str:
    for codes, description in SKY.items():
        if code in codes:
            return description
    return "con el cielo variable"


def fetch_open_meteo(latitude: float, longitude: float) -> dict:
    """The real call. Imported lazily so tests never touch the network."""
    import requests

    response = requests.get(
        API_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "hourly": "precipitation_probability",
            "timezone": "auto",
            # Two days, not one: at 22:00 the next six hours are mostly tomorrow.
            # The daily lists still start at today, so index 0 keeps meaning today.
            "forecast_days": 2,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


@dataclass(frozen=True)
class RainAhead:
    when: datetime
    chance: int


@dataclass(frozen=True)
class Forecast:
    temperature: int
    feels_like: int
    humidity: int
    maximum: int
    minimum: int
    rain_chance: int
    code: int


class WeatherClient:
    def __init__(
        self,
        latitude: float,
        longitude: float,
        place: str = "",
        fetch: Callable[[float, float], dict] = fetch_open_meteo,
        polish: Callable[..., str] = as_is,
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.place = place
        self.fetch = fetch
        self.polish = polish

    def now(self) -> Forecast:
        try:
            payload = self.fetch(self.latitude, self.longitude)
        except Exception as exc:
            log.warning("no se pudo consultar el clima: %s", exc)
            raise WeatherError(f"No pude consultar el clima: {exc}") from exc

        try:
            current = payload["current"]
            daily = payload["daily"]
            return Forecast(
                temperature=round(current["temperature_2m"]),
                feels_like=round(current["apparent_temperature"]),
                humidity=round(current["relative_humidity_2m"]),
                maximum=round(daily["temperature_2m_max"][0]),
                minimum=round(daily["temperature_2m_min"][0]),
                rain_chance=round(daily["precipitation_probability_max"][0]),
                code=int(current["weather_code"]),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise WeatherError(f"El servicio de clima contestó algo que no entiendo: {exc}") from exc

    def rain_ahead(self, now: datetime, hours: int = RAIN_WINDOW_HOURS) -> RainAhead | None:
        """The first hour in the window where rain is likely, or None.

        Open-Meteo answers in local time and without an offset (`timezone=auto`),
        so an aware clock is compared naive: the offset is already baked in.
        """
        try:
            payload = self.fetch(self.latitude, self.longitude)
        except Exception as exc:
            log.warning("no se pudo consultar el pronóstico por hora: %s", exc)
            raise WeatherError(f"No pude consultar el clima: {exc}") from exc

        hourly = payload.get("hourly") or {}
        moments = hourly.get("time") or []
        chances = hourly.get("precipitation_probability") or []

        start = now.replace(tzinfo=None)
        end = start + timedelta(hours=hours)
        for raw, chance in zip(moments, chances):
            try:
                moment = datetime.fromisoformat(raw)
            except (TypeError, ValueError):
                continue
            if chance is None or moment <= start or moment > end:
                continue
            if chance >= RAIN_ALERT_CHANCE:
                return RainAhead(when=moment, chance=int(chance))
        return None

    def spoken(self) -> str:
        """One or two sentences, written to be heard rather than read."""
        forecast = self.now()
        where = f" en {self.place}" if self.place else ""

        # Everything spelled out: "21 grados" was read as "veintiuno grados".
        parts = [
            f"Ahora{where} hay {number(forecast.temperature)} grados, "
            f"{describe_code(forecast.code)}."
        ]
        if abs(forecast.feels_like - forecast.temperature) >= FEELS_LIKE_GAP:
            parts.append(f"La sensación es de {number(forecast.feels_like)}.")
        parts.append(
            f"Máxima de {number(forecast.maximum)}, mínima de {number(forecast.minimum)}."
        )
        if forecast.rain_chance >= RAIN_WORTH_MENTIONING:
            parts.append(f"Probabilidad de lluvia, {number(forecast.rain_chance)} por ciento.")
        return self.polish(" ".join(parts), must_keep=[self.place] if self.place else [])


class RainWatcher:
    """Says once a day that rain is coming, while there is still time to react.

    At most one warning per day on purpose: the point is to bring the clothes
    in, not to narrate the sky. A second one the same day would be noise, and
    noise is how a warning gets ignored.
    """

    def __init__(
        self,
        weather: WeatherClient,
        announce: Callable[[str], None],
        marks,
        clock: Callable[[], datetime] = datetime.now,
        window_hours: int = RAIN_WINDOW_HOURS,
        polish: Callable[..., str] = as_is,
    ):
        self.weather = weather
        self.announce = announce
        self.marks = marks
        self.clock = clock
        self.window_hours = window_hours
        self.polish = polish

    def check(self) -> str | None:
        now = self.clock()
        already = self.marks.get(RAIN_MARK)
        if already is not None and already.date() == now.date():
            return None

        try:
            rain = self.weather.rain_ahead(now, hours=self.window_hours)
        except WeatherError:
            return None  # ya quedó en el log; la vuelta siguiente reintenta
        if rain is None:
            return None

        text = self.polish(
            f"Ojo, va a llover a eso de {spoken_clock(rain.when.hour, rain.when.minute)}."
        )
        try:
            self.announce(text)
        except Exception:
            # A warning that did not get out is not done: it retries next round.
            log.exception("no se pudo avisar de la lluvia")
            return None

        self.marks.set(RAIN_MARK, now)
        return text

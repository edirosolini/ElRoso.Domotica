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

# The other four warnings. Thresholds are module constants, like the rain ones:
# they are a judgement about this house and this city, not something to move
# from the container. The day one of them has to be tuned remotely, it goes to
# `Config` — and so does the rain.
HEAT_ALERT = 33
COLD_ALERT = 3
GUST_ALERT = 50
STORM_CODES = (95, 96, 99)

# 🔴 Heat and cold are about the day as a whole, so they wait for somebody to
# be awake: at four in the morning nobody needs today's high, and the quiet
# window would push it to the chat where it reads as noise. Wind and storm are
# about the next few hours and go out whenever they are seen.
DAY_ALERT_FROM = 7
DAY_ALERT_TO = 11

HEAT_MARK = "heat-alert"
COLD_MARK = "cold-alert"
WIND_MARK = "wind-alert"
STORM_MARK = "storm-alert"


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
            # Gusts and the sky code ride along: one request answers every
            # warning, and the forecast is free but not ours to hammer.
            "hourly": "precipitation_probability,wind_gusts_10m,weather_code",
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
class HourAhead:
    """One hour of the forecast, with everything a warning might look at."""

    when: datetime
    rain_chance: int
    gust: int
    code: int


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

    def hours_ahead(self, now: datetime, hours: int = RAIN_WINDOW_HOURS) -> list[HourAhead]:
        """The forecast hour by hour inside the window, from one request.

        Open-Meteo answers in local time and without an offset (`timezone=auto`),
        so an aware clock is compared naive: the offset is already baked in.
        """
        try:
            payload = self.fetch(self.latitude, self.longitude)
        except Exception as exc:
            log.warning("no se pudo consultar el pronóstico por hora: %s", exc)
            raise WeatherError(f"No pude consultar el clima: {exc}") from exc

        return self._hours_of(payload, now, hours)

    @staticmethod
    def _hours_of(payload: dict, now: datetime, hours: int) -> list[HourAhead]:
        hourly = payload.get("hourly") or {}
        moments = hourly.get("time") or []
        chances = hourly.get("precipitation_probability") or []
        gusts = hourly.get("wind_gusts_10m") or []
        codes = hourly.get("weather_code") or []

        start = now.replace(tzinfo=None)
        end = start + timedelta(hours=hours)
        ahead = []
        for index, raw in enumerate(moments):
            try:
                moment = datetime.fromisoformat(raw)
            except (TypeError, ValueError):
                continue
            if moment <= start or moment > end:
                continue

            def at(values, default=0):
                value = values[index] if index < len(values) else None
                return default if value is None else int(value)

            ahead.append(
                HourAhead(
                    when=moment,
                    rain_chance=at(chances),
                    gust=at(gusts),
                    code=at(codes),
                )
            )
        return ahead

    def day_ahead(self) -> tuple[int, int]:
        """Today's high and low, which is what a whole-day warning looks at."""
        forecast = self.now()
        return forecast.maximum, forecast.minimum

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


class WeatherWatcher:
    """The other four warnings of the sky: heat, cold, wind and storm.

    Same shape as `RainWatcher` and for the same reasons — once a day, and a
    warning that could not be said is not marked as done — with one difference
    that matters: 🔴 **each warning keeps its own mark**. A shared one would
    mean a hot day silences the gust that knocks the plants over, and nobody
    would ever find out why.

    The rain keeps its own watcher: its mark, its threshold and its test have
    history, and folding it in here would rewrite state that is already in the
    deployed database.
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

    def check(self) -> list[str]:
        """Everything worth saying right now, said. Usually nothing."""
        now = self.clock()
        said = []
        for mark, text in self._warnings(now):
            if not text or self._already_today(mark, now):
                continue
            try:
                self.announce(text)
            except Exception:
                # Not marked: it goes out on the next round, like the rain.
                log.exception("no se pudo avisar del clima")
                continue
            self.marks.set(mark, now)
            said.append(text)
        return said

    def _already_today(self, mark: str, now: datetime) -> bool:
        already = self.marks.get(mark)
        return already is not None and already.date() == now.date()

    def _warnings(self, now: datetime) -> list[tuple[str, str]]:
        found = []
        if DAY_ALERT_FROM <= now.hour < DAY_ALERT_TO:
            found.extend(self._day_warnings())
        found.extend(self._hour_warnings(now))
        return found

    def _day_warnings(self) -> list[tuple[str, str]]:
        try:
            maximum, minimum = self.weather.day_ahead()
        except WeatherError:
            return []  # ya quedó en el log; la vuelta siguiente reintenta

        found = []
        if maximum >= HEAT_ALERT:
            found.append((
                HEAT_MARK,
                self.polish(
                    f"Ojo con el calor: hoy la máxima es de {number(maximum)} grados."
                ),
            ))
        if minimum <= COLD_ALERT:
            found.append((
                COLD_MARK,
                self.polish(
                    f"Ojo con el frío: hoy la mínima es de {number(minimum)} grados."
                ),
            ))
        return found

    def _hour_warnings(self, now: datetime) -> list[tuple[str, str]]:
        try:
            ahead = self.weather.hours_ahead(now, hours=self.window_hours)
        except WeatherError:
            return []

        found = []
        gust = next((hour for hour in ahead if hour.gust >= GUST_ALERT), None)
        if gust is not None:
            found.append((
                WIND_MARK,
                self.polish(
                    f"Ojo, se viene viento a eso de {spoken_clock(gust.when.hour, gust.when.minute)}, "
                    f"con ráfagas de {number(gust.gust)} kilómetros por hora."
                ),
            ))

        storm = next((hour for hour in ahead if hour.code in STORM_CODES), None)
        if storm is not None:
            found.append((
                STORM_MARK,
                self.polish(
                    "Ojo, se viene tormenta a eso de "
                    f"{spoken_clock(storm.when.hour, storm.when.minute)}."
                ),
            ))
        return found

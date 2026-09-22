"""El clima, dicho en voz alta.

Usa Open-Meteo: gratis, sin cuenta y sin API key. Nada de acá depende del
Asistente de Google, que es lo que falla al preguntarle al parlante.
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

# Códigos de clima de la OMM, en las palabras que usaría una persona.
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

# Con menos diferencia que esta, decir la sensación térmica no agrega nada.
FEELS_LIKE_GAP = 3
RAIN_WORTH_MENTIONING = 20

# Hasta dónde mira el aviso de lluvia y qué tan seguro tiene que estar. Avisar
# de algo que es cara o ceca es cómo un aviso deja de leerse.
RAIN_WINDOW_HOURS = 6
RAIN_ALERT_CHANCE = 60
RAIN_MARK = "rain-alert"

# Umbrales de los otros cuatro avisos. Constantes del módulo, como los de lluvia.
HEAT_ALERT = 33
COLD_ALERT = 3
GUST_ALERT = 50
STORM_CODES = (95, 96, 99)

# El calor y el frío son sobre el día entero, así que esperan a que alguien
# esté despierto. El viento y la tormenta son sobre las próximas horas.
DAY_ALERT_FROM = 7
DAY_ALERT_TO = 11

HEAT_MARK = "heat-alert"
COLD_MARK = "cold-alert"
WIND_MARK = "wind-alert"
STORM_MARK = "storm-alert"


class WeatherError(Exception):
    """El pronóstico no se pudo traer o entender."""


def describe_code(code: int) -> str:
    for codes, description in SKY.items():
        if code in codes:
            return description
    return "con el cielo variable"


def fetch_open_meteo(latitude: float, longitude: float) -> dict:
    """La llamada real. Se importa tarde para que los tests no toquen la red."""
    import requests

    response = requests.get(
        API_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            # Las ráfagas y el código de cielo viajan con lo demás: un solo
            # pedido contesta todos los avisos.
            "hourly": "precipitation_probability,wind_gusts_10m,weather_code",
            "timezone": "auto",
            # Dos días, no uno: a las 22:00 las próximas seis horas caen casi
            # todas en mañana. Las listas diarias siguen empezando por hoy.
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
    """Una hora del pronóstico, con todo lo que un aviso pueda mirar."""

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
        """La primera hora de la ventana con lluvia probable, o None.

        Open-Meteo contesta en hora local y sin offset (`timezone=auto`), así
        que un reloj con zona se compara naive: el offset ya viene aplicado.
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
        """El pronóstico hora por hora dentro de la ventana, en un solo pedido.

        Open-Meteo contesta en hora local y sin offset (`timezone=auto`), así
        que un reloj con zona se compara naive: el offset ya viene aplicado.
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
        """La máxima y la mínima de hoy, que es lo que mira un aviso del día entero."""
        forecast = self.now()
        return forecast.maximum, forecast.minimum

    def spoken(self) -> str:
        """Una o dos oraciones, escritas para escucharse y no para leerse."""
        forecast = self.now()
        where = f" en {self.place}" if self.place else ""

        # Todo en palabras: Piper lee un dígito como cardinal masculino suelto.
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
    """Avisa una vez por día que se viene el agua, con tiempo para reaccionar.

    Un solo aviso por día a propósito: la idea es entrar la ropa, no narrar el
    cielo. Un segundo aviso el mismo día sería ruido.
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
            # Un aviso que no salió no está hecho: se reintenta en la próxima vuelta.
            log.exception("no se pudo avisar de la lluvia")
            return None

        self.marks.set(RAIN_MARK, now)
        return text


class WeatherWatcher:
    """Los otros cuatro avisos del cielo: calor, frío, viento y tormenta.

    Misma forma que `RainWatcher`: una vez por día, y lo que no se pudo decir
    no se marca. Cada aviso lleva su propia marca, así uno no tapa a otro. La
    lluvia sigue en su watcher aparte.
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
                # No se marca: sale en la vuelta siguiente, como la lluvia.
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

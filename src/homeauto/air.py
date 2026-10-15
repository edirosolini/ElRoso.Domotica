"""La calidad del aire de hoy, por Open-Meteo."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

log = logging.getLogger(__name__)

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEOUT = 15

# Horas, inclusive, en las que se busca el peor índice del día.
DAY_FROM = 8
DAY_TO = 20


class AirError(Exception):
    """La calidad del aire no se pudo traer o entender."""


def fetch_air_quality(latitude: float, longitude: float, get: Callable | None = None) -> dict:
    """Pide el índice de hoy hora por hora y devuelve el JSON; `get` reemplaza a `requests.get`."""
    if get is None:
        import requests

        get = requests.get

    response = get(
        API_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "us_aqi,pm2_5",
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


class AirClient:
    def __init__(
        self,
        latitude: float,
        longitude: float,
        fetch: Callable[[float, float], dict] = fetch_air_quality,
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.fetch = fetch

    def worst_today(self, now: datetime) -> int | None:
        """El peor `us_aqi` de hoy entre las ocho y las veinte, o None sin datos."""
        try:
            payload = self.fetch(self.latitude, self.longitude)
        except Exception as exc:
            log.warning("could not fetch the air quality: %s", exc)
            raise AirError(f"No pude consultar la calidad del aire: {exc}") from exc

        try:
            hourly = payload["hourly"]
            moments = hourly["time"]
            values = hourly["us_aqi"]
            today = now.replace(tzinfo=None).date()
            found = [
                value
                for raw, value in zip(moments, values)
                if value is not None
                and (moment := datetime.fromisoformat(raw)).date() == today
                and DAY_FROM <= moment.hour <= DAY_TO
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise AirError(f"El servicio de calidad del aire contestó algo que no entiendo: {exc}") from exc
        return round(max(found)) if found else None

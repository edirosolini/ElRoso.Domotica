"""Los tres números de la economía argentina, dichos en voz alta.

El dólar sale de dolarapi; el riesgo país y la inflación del mes, de
argentinadatos: APIs públicas, gratis y sin cuenta. Los tres son
independientes. Todo sale de acá en palabras, y una cifra que `verbalize` no
pueda decir se calla antes que decirla con dígitos.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable

from homeauto.polish import as_is
from homeauto.verbalize import decimal, number

log = logging.getLogger(__name__)

DOLLAR_URL = "https://dolarapi.com/v1/dolares/oficial"
RISK_URL = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais/ultimo"
INFLATION_URL = "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"
TIMEOUT = 15

MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


class EconomyError(Exception):
    """Una cifra no se pudo traer o entender."""


def fetch_json(url: str) -> dict | list:
    """La llamada real. Se importa tarde para que los tests no toquen la red."""
    import requests

    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


class EconomyClient:
    def __init__(
        self,
        fetch: Callable[[str], dict | list] = fetch_json,
        polish: Callable[..., str] = as_is,
    ):
        self.fetch = fetch
        self.polish = polish

    def _get(self, url: str) -> dict | list:
        try:
            return self.fetch(url)
        except Exception as exc:  # noqa: BLE001 - una fuente caída no es un error del resumen
            log.warning("no pude consultar %s: %s", url, exc)
            raise EconomyError(f"No pude consultar {url}: {exc}") from exc

    def dollar(self) -> int:
        """El dólar oficial, al precio que cuesta comprar uno."""
        payload = self._get(DOLLAR_URL)
        try:
            return round(float(payload["venta"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise EconomyError(f"el dólar vino raro: {exc}") from exc

    def country_risk(self) -> int:
        payload = self._get(RISK_URL)
        try:
            return round(float(payload["valor"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise EconomyError(f"el riesgo país vino raro: {exc}") from exc

    def inflation(self) -> tuple[str, float]:
        """El último mes publicado, por su nombre, y cuánto fue."""
        payload = self._get(INFLATION_URL)
        try:
            last = payload[-1]
            when = date.fromisoformat(last["fecha"])
            return MONTHS[when.month - 1], float(last["valor"])
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise EconomyError(f"la inflación vino rara: {exc}") from exc

    def spoken(self) -> str:
        """Una oración por cada cifra que contestó, o nada."""
        parts = [
            said
            for said in (self._dollar_line(), self._risk_line(), self._inflation_line())
            if said
        ]
        if not parts:
            return ""

        text = " ".join(parts)
        # Lo que el pulido no puede perder: el nombre de cada cifra. Cuáles
        # hay depende de quién contestó, así que la lista sale del texto.
        keep = tuple(term for term in ("dólar", "riesgo país", "inflación") if term in text)
        return self.polish(text, must_keep=keep)

    def _dollar_line(self) -> str:
        return self._line(
            lambda: f"El dólar oficial está a {number(self.dollar())} pesos."
        )

    def _risk_line(self) -> str:
        return self._line(
            lambda: f"El riesgo país, {number(self.country_risk())} puntos."
        )

    def _inflation_line(self) -> str:
        def said() -> str:
            month, value = self.inflation()
            return f"La inflación de {month} fue de {decimal(value)} por ciento."

        return self._line(said)

    @staticmethod
    def _line(source: Callable[[], str]) -> str:
        """Una cifra que no se puede traer, entender o decir se deja afuera.

        `verbalize` rechaza lo que no puede poner en palabras, y esa negativa
        termina acá: dejarla pasar pondría un dígito frente a Piper.
        """
        try:
            return source()
        except (EconomyError, ValueError):
            log.info("un número de la economía se queda afuera del resumen")
            return ""

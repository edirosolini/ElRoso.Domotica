"""The three numbers of the Argentine economy, read out loud.

Three public APIs, free and without an account, the same posture as the
weather: nothing here depends on anybody's key. The dollar comes from
dolarapi, the country risk and the monthly inflation from argentinadatos.

🔴 The three are independent. One that times out leaves a hole in the morning
summary, never cancels it — the same rule the briefing already applies to the
agenda, the sky and the services.

Everything leaves here spelled out in words. A figure this module cannot say —
past what `verbalize` covers — is dropped rather than spoken with digits: the
speaker reads "1535" as a loose masculine cardinal, and a wrong number said
confidently is worse than a number not said.
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
    """A figure could not be fetched or understood."""


def fetch_json(url: str) -> dict | list:
    """The real call. Imported lazily so tests never touch the network."""
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
        """The official dollar, at what it costs to buy one."""
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
        """The last month published, by its name, and how much it was."""
        payload = self._get(INFLATION_URL)
        try:
            last = payload[-1]
            when = date.fromisoformat(last["fecha"])
            return MONTHS[when.month - 1], float(last["valor"])
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise EconomyError(f"la inflación vino rara: {exc}") from exc

    def spoken(self) -> str:
        """One sentence per figure that answered, or nothing at all."""
        parts = [
            said
            for said in (self._dollar_line(), self._risk_line(), self._inflation_line())
            if said
        ]
        if not parts:
            return ""

        text = " ".join(parts)
        # What the rewrite may not lose: the name of each figure. Which ones
        # are there depends on who answered, so the list is built from the text.
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
        """A figure that cannot be fetched, understood or said is left out.

        🔴 `verbalize` refuses anything past what it can spell out, and that
        refusal has to end here: letting it through would put a digit in front
        of Piper, which is the whole reason this module speaks in words.
        """
        try:
            return source()
        except (EconomyError, ValueError):
            log.info("un número de la economía se queda afuera del resumen")
            return ""

"""Los feriados argentinos: se traen de argentinadatos y se leen de una caché local."""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

from homeauto.verbalize import cardinal

log = logging.getLogger(__name__)

URL = "https://api.argentinadatos.com/v1/feriados/{year}"
TIMEOUT = 15

FIXED = "inamovible"
MOVABLE = "trasladable"
BRIDGE = "puente"
# Los tipos que callan lo que saltea feriados; un puente suena.
SKIPPING = (FIXED, MOVABLE)

# Desde este mes se trae también el año siguiente.
NEXT_YEAR_FROM = 11

SCHEMA = """
CREATE TABLE IF NOT EXISTS holidays (
    day  TEXT    PRIMARY KEY,
    year INTEGER NOT NULL,
    kind TEXT    NOT NULL,
    name TEXT    NOT NULL
);
"""

_DATE_IN_PARENTHESES = re.compile(r"\s*\([^)]*\d+/\d+[^)]*\)")
_DIGIT = re.compile(r"\d")

# Las abreviaturas que se dicen enteras.
ABBREVIATIONS = {"Gral.": "General", "Dr.": "Doctor", "Sta.": "Santa", "Sto.": "Santo"}
_ABBREVIATION = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(short) for short in ABBREVIATIONS) + r")(?!\w)"
)
# Un romano en mayúsculas pegado atrás de un nombre propio: «León XIV».
_ROMAN_AFTER_NAME = re.compile(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñü]+) ([IVXL]+)\b")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50}
# Hasta dónde se leen romanos: de I a LXXXIX.
MAX_ROMAN = 89


class HolidayError(Exception):
    """Los feriados de un año no se pudieron traer o entender."""


def _roman(numeral: str) -> int | None:
    """El valor de un romano bien escrito, o None si no lo es."""
    total = 0
    for current, following in zip(numeral, numeral[1:] + " "):
        value = _ROMAN_VALUES[current]
        total += -value if _ROMAN_VALUES.get(following, 0) > value else value
    if not 0 < total <= MAX_ROMAN or _to_roman(total) != numeral:
        return None
    return total


def _to_roman(value: int) -> str:
    """El romano canónico de un número de uno a ochenta y nueve."""
    parts = ((50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    found = ""
    for amount, numeral in parts:
        while value >= amount:
            found += numeral
            value -= amount
    return found


def _say_roman(match: re.Match) -> str:
    """El nombre con su romano en palabras, o tal cual si el romano no es válido."""
    value = _roman(match.group(2))
    return f"{match.group(1)} {cardinal(value)}" if value is not None else match.group(0)


def spoken_name(name: str) -> str:
    """El nombre para decir: abreviaturas enteras y romanos de nombres propios en palabras."""
    name = _ABBREVIATION.sub(lambda match: ABBREVIATIONS[match.group(1)], name)
    return _ROMAN_AFTER_NAME.sub(_say_roman, name)


def clean_name(name: str) -> str:
    """El nombre sin el paréntesis con la fecha, como «(17/6)»."""
    return _DATE_IN_PARENTHESES.sub("", name).strip()


@dataclass(frozen=True)
class Holiday:
    day: date
    kind: str
    name: str

    @property
    def skips(self) -> bool:
        """Si calla lo que saltea feriados."""
        return self.kind in SKIPPING

    @property
    def spoken(self) -> str:
        """El párrafo hablado del resumen, sin dígitos."""
        if not self.skips:
            return "Hoy es día no laborable."
        said = spoken_name(self.name)
        if _DIGIT.search(said):
            return "Hoy es feriado."
        return f"Hoy es feriado: {said}."

    @property
    def written(self) -> str:
        """El párrafo escrito del resumen, con el nombre tal cual."""
        if not self.skips:
            return "Hoy es día no laborable."
        return f"Hoy es feriado: {self.name}."


def fetch_json(url: str) -> list:
    """La llamada HTTP real: el JSON que devuelve `url`."""
    import requests

    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


class HolidayClient:
    def __init__(self, fetch: Callable[[str], list] = fetch_json):
        self.fetch = fetch

    def year(self, year: int) -> list[Holiday]:
        """Los feriados de un año, con el nombre limpio."""
        url = URL.format(year=year)
        try:
            payload = self.fetch(url)
        except Exception as exc:  # noqa: BLE001
            raise HolidayError(f"No pude consultar {url}: {exc}") from exc
        try:
            return [
                Holiday(date.fromisoformat(item["fecha"]), item["tipo"], clean_name(item["nombre"]))
                for item in payload
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise HolidayError(f"los feriados de {year} vinieron raros: {exc}") from exc


def _row_to_holiday(row: sqlite3.Row) -> Holiday:
    return Holiday(date.fromisoformat(row["day"]), row["kind"], row["name"])


class HolidayStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def replace(self, year: int, holidays: Iterable[Holiday]) -> None:
        """Reemplaza los feriados de un año, en una sola transacción."""
        rows = [(h.day.isoformat(), year, h.kind, h.name) for h in holidays]
        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                conn.execute("DELETE FROM holidays WHERE year = ?", (year,))
                conn.executemany(
                    "INSERT OR REPLACE INTO holidays (day, year, kind, name) VALUES (?, ?, ?, ?)",
                    rows,
                )
            except Exception:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    def get(self, day: date) -> Holiday | None:
        """El feriado de ese día, o None."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM holidays WHERE day = ?", (day.isoformat(),)).fetchone()
        return _row_to_holiday(row) if row else None

    def between(self, start: date, end: date) -> list[Holiday]:
        """Los feriados desde `start` hasta antes de `end`, en orden."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM holidays WHERE day >= ? AND day < ? ORDER BY day",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return [_row_to_holiday(row) for row in rows]


def refresh(client: HolidayClient, store: HolidayStore, today: date) -> None:
    """Trae el año en curso, y desde noviembre el siguiente; lo que falla deja la caché."""
    years = [today.year] + ([today.year + 1] if today.month >= NEXT_YEAR_FROM else [])
    for year in years:
        try:
            found = client.year(year)
        except HolidayError as exc:
            log.warning("could not refresh the holidays of %s: %s", year, exc)
            continue
        if not found:
            log.warning("no holidays came for %s; keeping the cache", year)
            continue
        store.replace(year, found)
        log.info("holidays of %s refreshed: %s", year, len(found))

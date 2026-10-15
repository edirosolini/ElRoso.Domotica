"""Cuántas dosis quedan de cada remedio y cuándo avisar que hay que comprar."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Con cuántas dosis o menos se avisa que hay que comprar.
STOCK_ALERT = 7

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS pill_stock (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    count     INTEGER NOT NULL DEFAULT 0,
    threshold INTEGER NOT NULL DEFAULT {STOCK_ALERT},
    alerted   INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class Stock:
    id: int
    name: str
    count: int
    threshold: int = STOCK_ALERT
    alerted: bool = False


def _row_to_stock(row: sqlite3.Row) -> Stock:
    return Stock(
        id=row["id"],
        name=row["name"],
        count=row["count"],
        threshold=row["threshold"],
        alerted=bool(row["alerted"]),
    )


def _key(name: str) -> str:
    """El nombre como se guarda: sin espacios de más y en minúsculas."""
    return " ".join(name.split()).lower()


class StockStore:
    """Una fila por remedio: la tabla dieciséis de `jobs.db`, dueña de su esquema."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def all(self) -> list[Stock]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM pill_stock ORDER BY name").fetchall()
        return [_row_to_stock(row) for row in rows]

    def get(self, stock_id: int) -> Stock | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM pill_stock WHERE id = ?", (stock_id,)).fetchone()
        return _row_to_stock(row) if row else None

    def find(self, name: str) -> Stock | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM pill_stock WHERE name = ?", (_key(name),)).fetchone()
        return _row_to_stock(row) if row else None

    def ensure(self, name: str, count: int) -> tuple[Stock, bool]:
        """El stock con ese nombre, creado con `count` si no existía; True si lo creó."""
        with self._connect() as conn:
            created = conn.execute(
                "INSERT INTO pill_stock (name, count) VALUES (?, ?) ON CONFLICT(name) DO NOTHING",
                (_key(name), max(count, 0)),
            ).rowcount
        return self.find(name), bool(created)

    def take_dose(self, stock_id: int) -> tuple[Stock, bool] | None:
        """Descuenta una dosis sin bajar de cero; True si recién cruzó el umbral."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            changed = conn.execute(
                "UPDATE pill_stock SET count = MAX(count - 1, 0) WHERE id = ?", (stock_id,)
            ).rowcount
            if not changed:
                conn.execute("COMMIT")
                return None
            alert = conn.execute(
                "UPDATE pill_stock SET alerted = 1"
                " WHERE id = ? AND alerted = 0 AND count <= threshold",
                (stock_id,),
            ).rowcount
            conn.execute("COMMIT")
        return self.get(stock_id), bool(alert)

    def restock(self, name: str, amount: int) -> Stock | None:
        """Suma dosis y rearma el aviso si quedó por encima del umbral; None si no existe."""
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE pill_stock SET count = count + ?,"
                " alerted = CASE WHEN count + ? > threshold THEN 0 ELSE alerted END"
                " WHERE name = ?",
                (amount, amount, _key(name)),
            ).rowcount
        return self.find(name) if changed else None

    def set_count(self, name: str, count: int) -> Stock | None:
        """Fija lo que queda y rearma el aviso si quedó por encima del umbral; None si no existe."""
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE pill_stock SET count = ?,"
                " alerted = CASE WHEN ? > threshold THEN 0 ELSE alerted END"
                " WHERE name = ?",
                (max(count, 0), max(count, 0), _key(name)),
            ).rowcount
        return self.find(name) if changed else None

    def set_threshold(self, name: str, threshold: int) -> Stock | None:
        """Cambia el umbral y rearma el aviso si lo que queda está por encima; None si no existe."""
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE pill_stock SET threshold = ?,"
                " alerted = CASE WHEN count > ? THEN 0 ELSE alerted END"
                " WHERE name = ?",
                (threshold, threshold, _key(name)),
            ).rowcount
        return self.find(name) if changed else None

"""Las listas de la casa: qué falta comprar y qué falta hacer.

Dos listas fijas y no un nombre libre: "agregá a X Y" no se puede partir sin
adivinar dónde termina el nombre. Una tercera es una línea en `_NAMES`.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

SHOPPING = "compras"
TODO = "pendientes"
LISTS = (SHOPPING, TODO)

# Cómo la nombra la gente, incluida la forma que devuelve el intérprete.
_NAMES = {
    "compras": SHOPPING,
    "compra": SHOPPING,
    "supermercado": SHOPPING,
    "súper": SHOPPING,
    "super": SHOPPING,
    "mandados": SHOPPING,
    "pendientes": TODO,
    "pendiente": TODO,
    "tareas": TODO,
    "tarea": TODO,
    "cosas": TODO,
    "hacer": TODO,
}
_NOISE = ("la ", "el ", "las ", "los ", "lista de ", "lista ", "mi ")
# Los ítems de una lista, como los separa una persona: "leche, pan y yerba".
_ITEMS = re.compile(r"\s*,\s*|\s+y\s+")

SCHEMA = """
CREATE TABLE IF NOT EXISTS list_items (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    list_name TEXT NOT NULL,
    item      TEXT NOT NULL
);
"""

# Columnas sumadas después: una base vieja las recibe al abrirse.
COLUMNS = {"added_at": "TEXT"}


class ListError(Exception):
    """No existe esa lista."""


def resolve(name: str) -> str:
    """El nombre canónico de una lista, o `ListError` si no es ninguna."""
    clean = name.strip().lower().strip(".,")
    changed = True
    while changed:
        changed = False
        for noise in _NOISE:
            if clean.startswith(noise):
                clean = clean[len(noise):].strip()
                changed = True
    try:
        return _NAMES[clean]
    except KeyError:
        raise ListError(
            f"No tengo una lista de {name.strip()}. Tengo: {', '.join(LISTS)}."
        ) from None


def split_items(text: str) -> list[str]:
    """Los ítems de un texto, separados por comas y por «y», sin vacíos."""
    return [item.strip() for item in _ITEMS.split(text) if item.strip()]


class ListStore:
    """Una fila por ítem: la octava tabla de `jobs.db`, dueña de su esquema."""

    def __init__(self, db_path: Path | str, clock: Callable[[], datetime] = datetime.now):
        self.db_path = Path(db_path)
        self.clock = clock
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._add_missing_columns(conn)

    @staticmethod
    def _add_missing_columns(conn: sqlite3.Connection) -> None:
        """Agrega las columnas que la tabla no tiene."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(list_items)")}
        for name, definition in COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE list_items ADD COLUMN {name} {definition}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def items(self, list_name: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT item FROM list_items WHERE list_name = ? ORDER BY id",
                (list_name,),
            ).fetchall()
        return [row["item"] for row in rows]

    def add(self, list_name: str, items: list[str]) -> list[str]:
        """Suma lo que no estuviera ya. Devuelve lo que entró de verdad."""
        present = {item.lower() for item in self.items(list_name)}
        added = []
        for raw in items:
            item = raw.strip()
            if not item or item.lower() in present:
                continue
            present.add(item.lower())
            added.append(item)

        if added:
            at = self.clock().isoformat()
            with self._connect() as conn:
                conn.executemany(
                    "INSERT INTO list_items (list_name, item, added_at) VALUES (?, ?, ?)",
                    [(list_name, item, at) for item in added],
                )
        return added

    def remove(self, list_name: str, position: int) -> str | None:
        """Saca el ítem que ocupa esa posición, o None si no hay ninguno ahí."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, item FROM list_items WHERE list_name = ? ORDER BY id",
                (list_name,),
            ).fetchall()
            if not 1 <= position <= len(rows):
                return None
            row = rows[position - 1]
            conn.execute("DELETE FROM list_items WHERE id = ?", (row["id"],))
        return row["item"]

    def entries(self, list_name: str) -> list[tuple[int, str]]:
        """Los ítems con su id, que no cambia cuando se saca otro."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, item FROM list_items WHERE list_name = ? ORDER BY id",
                (list_name,),
            ).fetchall()
        return [(row["id"], row["item"]) for row in rows]

    def remove_id(self, list_name: str, item_id: int) -> str | None:
        """Saca el ítem con ese id de esa lista, o None si ya no está."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT item FROM list_items WHERE id = ? AND list_name = ?",
                (item_id, list_name),
            ).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM list_items WHERE id = ?", (item_id,))
        return row["item"]

    def clear(self, list_name: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM list_items WHERE list_name = ?", (list_name,))
        return cursor.rowcount

    def older_than(
        self, before: datetime, list_name: str | None = None
    ) -> list[tuple[int, str, str, datetime]]:
        """Los ítems agregados antes de `before`, con id, lista, texto y fecha; sin los sin fecha.

        Con `list_name`, solo los de esa lista.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, list_name, item, added_at FROM list_items"
                " WHERE added_at IS NOT NULL AND added_at < ?"
                " AND (? IS NULL OR list_name = ?) ORDER BY id",
                (before.isoformat(), list_name, list_name),
            ).fetchall()
        return [
            (row["id"], row["list_name"], row["item"], datetime.fromisoformat(row["added_at"]))
            for row in rows
        ]

    def undated(self, list_name: str | None = None) -> int:
        """Cuántos ítems no tienen fecha de alta; con `list_name`, solo de esa lista."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM list_items WHERE added_at IS NULL"
                " AND (? IS NULL OR list_name = ?)",
                (list_name, list_name),
            ).fetchone()
        return row[0]

    def remove_old(self, ids: Iterable[int], before: datetime) -> int:
        """Saca los ítems de `ids` que siguen siendo de antes de `before`."""
        ids = list(ids)
        if not ids:
            return 0
        marks = ", ".join("?" * len(ids))
        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM list_items WHERE id IN ({marks})"
                " AND added_at IS NOT NULL AND added_at < ?",
                (*ids, before.isoformat()),
            )
        return cursor.rowcount

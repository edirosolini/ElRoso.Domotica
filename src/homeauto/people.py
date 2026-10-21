"""El nombre de cada chat de la casa, como lo muestra Telegram, y el padrón de las personas."""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    chat_id INTEGER PRIMARY KEY,
    name    TEXT    NOT NULL
);
"""


def display_name(chat_id: int, names: dict[int, str]) -> str:
    """El nombre guardado del chat, o «Chat <id>» si todavía no escribió."""
    return names.get(chat_id) or f"Chat {chat_id}"


class People:
    """Anota el nombre de quien escribe, solo si su chat es de la casa."""

    def __init__(self, store: "PeopleStore", chat_ids):
        self.store = store
        self.chat_ids = frozenset(chat_ids)

    def meet(self, chat_id: int, name: str) -> None:
        if chat_id in self.chat_ids:
            self.store.remember(chat_id, name)


class PeopleStore:
    """Una fila por chat con el último nombre visto, dueña de su esquema."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(self, chat_id: int, name: str) -> None:
        """Guarda el nombre del chat; uno vacío no pisa al que había."""
        name = name.strip()
        if not name:
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO people (chat_id, name) VALUES (?, ?)"
                " ON CONFLICT(chat_id) DO UPDATE SET name = excluded.name",
                (chat_id, name),
            )

    def names(self) -> dict[int, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT chat_id, name FROM people").fetchall()
        return {row["chat_id"]: row["name"] for row in rows}


# Un nombre que se dice en voz alta: letras y espacios, sin dígitos ni guiones.
SAYABLE_NAME = re.compile(r"^[^\W\d_]+(?:\s+[^\W\d_]+)*$")
MAX_NAME = 40
# Palabras que la casa usa para otra cosa.
RESERVED = frozenset({"todos", "nadie"})

PERSONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL,
    chat_id INTEGER UNIQUE
);
"""

_KEEP = object()


@dataclass(frozen=True)
class Person:
    id: int
    name: str
    chat_id: int | None


@dataclass(frozen=True)
class Roster:
    """Todas las personas y todos los chats de la casa."""

    person_ids: frozenset[int]
    chats: frozenset[int]


class PersonError(ValueError):
    """Un cambio del padrón que no se puede hacer; el texto es para la persona."""


class PersonNotFound(PersonError):
    pass


class PersonStore:
    """Una fila por persona de la casa, con su chat si tiene; dueña de su esquema."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(PERSONS_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def all(self) -> list[Person]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, name, chat_id FROM persons ORDER BY id").fetchall()
        return [Person(row["id"], row["name"], row["chat_id"]) for row in rows]

    def get(self, person_id: int) -> Person | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, chat_id FROM persons WHERE id = ?", (person_id,)
            ).fetchone()
        return Person(row["id"], row["name"], row["chat_id"]) if row else None

    def add(self, name: str, chat_id: int | None) -> Person:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO persons (name, chat_id) VALUES (?, ?)", (name, chat_id)
            )
        return Person(cursor.lastrowid, name, chat_id)

    def update(self, person_id: int, name: str, chat_id: int | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE persons SET name = ?, chat_id = ? WHERE id = ?",
                (name, chat_id, person_id),
            )

    def remove(self, person_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))


class Household:
    """El padrón de la casa: valida altas y cambios y dice quién es quién."""

    def __init__(
        self,
        store: PersonStore,
        chat_ids: Iterable[int],
        before_remove: Callable[[Person], None] | None = None,
    ):
        self.store = store
        self.chat_ids = frozenset(chat_ids)
        # Lo que se hace con lo de una persona antes de borrarla.
        self.before_remove = before_remove
        self._lock = threading.Lock()

    def _live(self, person: Person) -> Person:
        """La persona con su chat solo si ese chat sigue siendo de la casa."""
        if person.chat_id is None or person.chat_id in self.chat_ids:
            return person
        return Person(person.id, person.name, None)

    def list(self) -> list[Person]:
        """Todas las personas, por nombre."""
        people = [self._live(person) for person in self.store.all()]
        return sorted(people, key=lambda person: (person.name.casefold(), person.id))

    def get(self, person_id: int) -> Person | None:
        person = self.store.get(person_id)
        return self._live(person) if person is not None else None

    def by_chat(self, chat_id: int) -> Person | None:
        """La persona dueña de ese chat, si el chat es de la casa."""
        return next((person for person in self.list() if person.chat_id == chat_id), None)

    def roster(self) -> Roster:
        people = self.list()
        chats = {person.chat_id for person in people if person.chat_id is not None}
        return Roster(
            person_ids=frozenset(person.id for person in people),
            chats=frozenset(chats | self.chat_ids),
        )

    def add(self, name: object, chat_id: object = None) -> Person:
        with self._lock:
            name = self._check_name(name, None)
            chat_id = self._check_chat(chat_id, None)
            return self.store.add(name, chat_id)

    def update(self, person_id: int, name: object = _KEEP, chat_id: object = _KEEP) -> Person:
        """Cambia el nombre, el chat o los dos; si algo no vale, no cambia nada."""
        with self._lock:
            person = self._existing(person_id)
            if name is not _KEEP:
                name = self._check_name(name, person_id)
            if chat_id is not _KEEP:
                chat_id = self._check_chat(chat_id, person_id)
            changed = Person(
                person_id,
                person.name if name is _KEEP else name,
                person.chat_id if chat_id is _KEEP else chat_id,
            )
            self.store.update(person_id, changed.name, changed.chat_id)
            return self._live(changed)

    def rename(self, person_id: int, name: object) -> Person:
        return self.update(person_id, name=name)

    def set_chat(self, person_id: int, chat_id: object) -> Person:
        return self.update(person_id, chat_id=chat_id)

    def remove(self, person_id: int) -> Person:
        """Borra a la persona y devuelve quién era."""
        with self._lock:
            person = self._live(self._existing(person_id))
            if self.before_remove is not None:
                self.before_remove(person)
            self.store.remove(person_id)
            return person

    def _existing(self, person_id: int) -> Person:
        person = self.store.get(person_id)
        if person is None:
            raise PersonNotFound(f"No existe la persona #{person_id}.")
        return person

    def _check_name(self, name: object, person_id: int | None) -> str:
        """El nombre ordenado, si se puede decir y nadie más lo tiene."""
        name = " ".join(name.split()) if isinstance(name, str) else ""
        if not name:
            raise PersonError("Falta el nombre.")
        if len(name) > MAX_NAME:
            raise PersonError(f"El nombre no puede pasar de {MAX_NAME} caracteres.")
        if not SAYABLE_NAME.fullmatch(name):
            raise PersonError(
                f"«{name}» no se puede decir en voz alta: un nombre va sin números ni guiones."
            )
        if name.casefold() in RESERVED:
            raise PersonError(f"«{name}» está reservado: elegí otro nombre.")
        for other in self.store.all():
            if other.id != person_id and other.name.casefold() == name.casefold():
                raise PersonError(f"Ya hay alguien que se llama {other.name}.")
        return name

    def _check_chat(self, chat_id: object, person_id: int | None) -> int | None:
        """El chat, si es de la casa y no es de otra persona; None es sin Telegram."""
        if chat_id is None:
            return None
        if type(chat_id) is not int or chat_id not in self.chat_ids:
            raise PersonError("Ese chat no es de la casa.")
        for other in self.store.all():
            if other.id != person_id and other.chat_id == chat_id:
                raise PersonError(f"Ese chat ya es de {other.name}.")
        return chat_id

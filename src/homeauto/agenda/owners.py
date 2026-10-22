"""De quién es un evento de Google: por el prefijo «[Nombre]» del título o por su calendario."""

from __future__ import annotations

import re
import unicodedata

# El nombre reservado que hace a un evento de todos.
EVERYONE = "todos"

_PREFIX = re.compile(r"\[([^\W\d_]+(?: [^\W\d_]+)*)\]\s*")


def fold(text: str) -> str:
    """El texto sin mayúsculas ni acentos, para comparar nombres."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _matching(name: str, names: dict[int, str]) -> list[int]:
    """Los ids del padrón cuyo nombre plegado es el de `name`."""
    wanted = fold(name)
    return [person_id for person_id, known in names.items() if fold(known) == wanted]


def _whom(ids: list[int], names: dict[int, str]) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Los ids sin repetir, en orden, con su nombre del padrón."""
    unique = tuple(dict.fromkeys(ids))
    return unique, tuple(names[person_id] for person_id in unique)


def owners(
    title: str, names: dict[int, str]
) -> tuple[tuple[int, ...], tuple[str, ...], str]:
    """Los ids, los nombres y el resto del título; todo o nada, y sin dueño el título tal cual."""
    text = title.strip()
    found: list[str] = []
    position = 0
    while match := _PREFIX.match(text, position):
        found.append(match.group(1))
        position = match.end()
    if not found or not names:
        return (), (), title
    rest = text[position:]
    if any(fold(name) == EVERYONE for name in found):
        return (), (EVERYONE,), rest
    ids: list[int] = []
    for name in found:
        matched = _matching(name, names)
        if not matched:
            return (), (), title
        ids.extend(matched)
    return (*_whom(ids, names), rest)


def calendar_owner(alias: str, names: dict[int, str]) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Los ids y nombres de la persona que se llama como el calendario; vacío si no es nadie."""
    return _whom(_matching(alias, names), names)

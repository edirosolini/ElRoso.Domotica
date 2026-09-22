"""Lectura de la lista de servicios a vigilar.

Un archivo en vez de variables de entorno: cada servicio necesita nombre,
destino, respuesta esperada y urgencia, y eso en una línea de .env es ilegible.
"""

from __future__ import annotations

import json
from pathlib import Path

from homeauto.watch.checks import Check

ALLOWED_FIELDS = {"name", "url", "host", "port", "expect", "urgent", "timeout", "attempts"}


class ChecksError(Exception):
    """El archivo existe pero no se puede usar."""


def load_checks(path: Path | str) -> list[Check]:
    path = Path(path)
    if not path.is_file():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ChecksError(f"{path}: JSON inválido: {exc}") from exc

    if not isinstance(payload, list):
        raise ChecksError(f"{path}: se esperaba una lista de servicios")

    checks: list[Check] = []
    seen: set[str] = set()
    for entry in payload:
        if not isinstance(entry, dict):
            raise ChecksError(f"{path}: cada servicio tiene que ser un objeto")

        # Un typo silencioso en "urgent" significaría que nunca te despierta.
        unknown = set(entry) - ALLOWED_FIELDS
        if unknown:
            raise ChecksError(f"{path}: campos desconocidos: {', '.join(sorted(unknown))}")

        try:
            check = Check(**entry)
        except (TypeError, ValueError) as exc:
            raise ChecksError(f"{path}: {exc}") from exc

        if check.name in seen:
            raise ChecksError(f"{path}: nombre repetido: '{check.name}'")
        seen.add(check.name)
        checks.append(check)

    return checks

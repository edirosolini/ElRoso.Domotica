"""Reading the list of services to watch.

A file instead of environment variables: each service needs a name, a target,
an expected answer and an urgency, and that in a .env line is unreadable.
"""

from __future__ import annotations

import json
from pathlib import Path

from homeauto.watch.checks import Check

ALLOWED_FIELDS = {"name", "url", "host", "port", "expect", "urgent", "timeout", "attempts"}


class ChecksError(Exception):
    """The file exists but cannot be used."""


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

        # A silent typo in "urgent" would mean it never wakes you up.
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

"""La frase con la que la casa llama a alguien a algo.

Un llamado trae la intención, no las palabras, así que la frase la escribe la
casa. Eso lo vuelve texto generado: pasa por el pulidor y no le aplica
`Router._faithful()`.
"""

from __future__ import annotations

import re
from datetime import datetime

from homeauto.correct import meal_verb

CALL = "Vengan a {what}."

# Un llamado a comer que no dice cuál comida es. Lo dice el reloj.
GENERIC_MEALS = frozenset({"comer", "comida", "la comida", "morfar"})

_TRAILING = re.compile(r"[.!?¡¿\s]+$")


def phrase(what: str, now: datetime) -> str:
    """Qué decir en voz alta para llamar a la casa a algo."""
    what = _TRAILING.sub("", what.strip()).strip()
    what = re.sub(r"^a\s+", "", what, flags=re.IGNORECASE).strip()

    if not what or what.lower() in GENERIC_MEALS:
        what = meal_verb(now)
    return CALL.format(what=what)

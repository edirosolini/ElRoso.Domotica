"""The sentence the house says when it calls people to something.

"llamar a todos a cenar" does not carry the words to say: it carries the
intention. The house writes the sentence, which makes it generated text like
the weather or the agenda — it goes through the polisher, and it is *not*
subject to `Router._faithful()`, because there is nothing to be faithful to.

⚠️ This is the line that separates it from `/decir`: there the words are the
person's and may not change; here there are no words yet.
"""

from __future__ import annotations

import re
from datetime import datetime

from homeauto.correct import meal_verb

CALL = "Vengan a {what}."

# A call to eat that does not say which meal it is. The clock says it.
GENERIC_MEALS = frozenset({"comer", "comida", "la comida", "morfar"})

_TRAILING = re.compile(r"[.!?¡¿\s]+$")


def phrase(what: str, now: datetime) -> str:
    """What to say out loud to call the house to something."""
    what = _TRAILING.sub("", what.strip()).strip()
    what = re.sub(r"^a\s+", "", what, flags=re.IGNORECASE).strip()

    if not what or what.lower() in GENERIC_MEALS:
        what = meal_verb(now)
    return CALL.format(what=what)

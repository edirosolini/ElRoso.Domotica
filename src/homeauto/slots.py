"""What a command is still missing before it can run.

The router names the command; this says whether the command has enough to work
with. It exists so that "creá una alarma" becomes a question instead of the
parser's complaint: the person did not write a bad argument, they wrote half of
a good one.

🔴 It never fills anything in. Deciding that an alarm with no hour means seven
in the morning is how the house ends up waking somebody nobody asked to wake.
The datum comes from the person, always.

⚠️ The shape of an alarm is checked in two places: here and in `Commands.alarm`.
They have to agree, and `tests/bot/test_conversation.py` ties them together —
anything this module calls incomplete, the real command has to refuse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from homeauto.route import strip_target
from homeauto.timespec import TOMORROW_WORDS, TimeSpecError, parse_duration, parse_weekdays

# The words that already say how an alarm repeats. `Commands.alarm` reads the
# same tuple, so a new one is added once.
DAILY_WORDS = ("diaria", "diario", "daily")

_CLOCK = re.compile(r"\d{1,2}[:.]\d{2}")
_DIGIT = re.compile(r"\d")
# «en comedor» with nothing after it: a device was named and the message never
# arrived. `strip_target` leaves it alone —it only drops a prefix that has
# something behind it— so here it counts as empty.
_TARGET_ONLY = re.compile(r"^en\s+[a-z0-9_-]+(?:\s*,\s*[a-z0-9_-]+)*$", re.IGNORECASE)


@dataclass(frozen=True)
class Slot:
    """A missing datum: its name, and what to ask for it.

    The question goes to the chat and never to the synthesizer, so unlike
    everything the house says out loud it is allowed to carry digits.
    """

    name: str
    question: str


TIME = Slot("hora", "¿A qué hora?")
DELAY = Slot("hora", "¿Dentro de cuánto?")
MESSAGE = Slot("mensaje", "¿Qué querés que diga?")
REPEAT = Slot("repeticion", "¿Una sola vez, todos los días, o algunos días?")
NUMBER = Slot("numero", "¿Cuál cancelo? El número sale en /lista.")
VOLUME = Slot("volumen", "¿Qué volumen? De cero a cien.")
DEVICE = Slot("equipo", "¿En qué equipo?")


def missing(command: str, argument: str) -> Slot | None:
    """The first datum the command still needs, or None when it can run."""
    check = _CHECKS.get(command)
    return check(_payload(argument)) if check else None


def _payload(argument: str) -> str:
    """What the command carries, with any targeting taken off the front."""
    text = strip_target(argument).strip()
    return "" if _TARGET_ONLY.fullmatch(text) else text


def _looks_like_time(token: str) -> bool:
    if _CLOCK.fullmatch(token):
        return True
    try:
        parse_duration(token)
    except TimeSpecError:
        return False
    return True


def _timed(text: str, when: Slot) -> Slot | None:
    """Whether a "<cuándo> <mensaje>" still misses one of its two halves."""
    text = text.strip()
    if not text:
        return when

    head, _, tail = text.partition(" ")
    if head.lower() in TOMORROW_WORDS:
        head, _, tail = tail.strip().partition(" ")
        if not head:
            return when

    if not _looks_like_time(head):
        return when
    if not tail.strip():
        return MESSAGE
    return None


def _alarm(argument: str) -> Slot | None:
    if not argument:
        return TIME

    head, _, tail = argument.partition(" ")
    if head.lower() in DAILY_WORDS or parse_weekdays(head):
        # How it repeats is already said; what is left is the hour and the text.
        return _timed(tail, TIME)

    # A one-off alarm is a complete order, but not an obvious one: it is the
    # owner's call to ask rather than schedule a single shot in silence.
    return _timed(argument, TIME) or REPEAT


def _numbered(slot: Slot):
    return lambda argument: None if _DIGIT.search(argument) else slot


def _needed(slot: Slot):
    return lambda argument: slot if not argument else None


_CHECKS = {
    "alarma": _alarm,
    "timer": lambda argument: _timed(argument, DELAY),
    "decir": _needed(MESSAGE),
    "cancelar": _numbered(NUMBER),
    "volumen": _numbered(VOLUME),
    "usar": _needed(DEVICE),
}

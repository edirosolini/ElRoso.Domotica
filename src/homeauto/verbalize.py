"""Numbers and clock times written out in words, for the synthesizer.

Piper reads a digit as the bare masculine cardinal: "1 cosa" comes out as
"uno cosa", and "a las 21" as "a las veintiuno". Anything meant to be heard has
to reach it already spelled out, agreeing in gender with the noun it modifies.

This is deliberately a plain function and not a smarter rewriter: an
announcement has to say exactly what it was given, and the same phrase must
always produce the same audio or the synthesis cache stops working.
"""

from __future__ import annotations

import re
from collections import Counter

MASCULINE = "m"
FEMININE = "f"

_UNITS = (
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
    "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete",
    "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés",
    "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve",
)
_TENS = {
    3: "treinta", 4: "cuarenta", 5: "cincuenta",
    6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa",
}
_HUNDREDS = {
    1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos", 5: "quinientos",
    6: "seiscientos", 7: "setecientos", 8: "ochocientos", 9: "novecientos",
}

# Money is what pushed this past three digits: a dollar at one thousand five
# hundred could not be said at all, so no economic figure could reach the
# speaker. Millions stay out — nothing this house says counts that high, and a
# number nobody checks is a number that will be read wrong.
MAXIMUM = 999_999


def _apocopate(word: str) -> str:
    """"veintiuno" -> "veintiún": the form a number takes before a noun."""
    if word.endswith("veintiuno"):
        return f"{word[:-len('veintiuno')]}veintiún"
    if word.endswith("uno"):
        return f"{word[:-len('uno')]}un"
    return word


def _cardinal(value: int) -> str:
    """0-999999 in plain masculine, before any agreement is applied."""
    if value >= 1000:
        thousands, rest = divmod(value, 1000)
        # "un mil" is not Spanish, and the count before "mil" is always
        # apocopated: "veintiún mil", never "veintiuno mil".
        head = "mil" if thousands == 1 else f"{_apocopate(_cardinal(thousands))} mil"
        return head if rest == 0 else f"{head} {_cardinal(rest)}"
    if value < 30:
        return _UNITS[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        return _TENS[tens] if ones == 0 else f"{_TENS[tens]} y {_UNITS[ones]}"
    if value == 100:
        return "cien"
    hundreds, rest = divmod(value, 100)
    return _HUNDREDS[hundreds] if rest == 0 else f"{_HUNDREDS[hundreds]} {_cardinal(rest)}"


def number(value: int, gender: str = MASCULINE) -> str:
    """A number as it is said *before a noun*: "un minuto", "veintiuna cosas".

    That is the only shape this project needs — every number it says out loud
    is counting something — so the masculine form is the apocopated one.
    """
    if abs(value) > MAXIMUM:
        raise ValueError(f"fuera de rango para decir en voz alta: {value}")
    if value < 0:
        return f"menos {number(-value, gender)}"

    word = _cardinal(value)
    if gender == FEMININE:
        # Only what comes after the last "mil" agrees: "mil doscientas cosas",
        # but "veintiún mil", because there the noun being counted is "mil".
        head, separator, tail = word.rpartition("mil")
        if separator:
            return f"{head}{separator}{_feminine(tail)}"
        return _feminine(word)

    return _apocopate(word)


def _feminine(word: str) -> str:
    if word.endswith("veintiuno"):
        word = f"{word[:-len('veintiuno')]}veintiuna"
    elif word.endswith("uno"):
        word = f"{word[:-len('uno')]}una"
    return word.replace("cientos", "cientas")


def decimal(value: float, gender: str = MASCULINE) -> str:
    """A number with a fraction, the way it is read: "dos coma uno".

    Written as digits, "2,1" reaches Piper as two separate numbers with the
    comma swallowed. Inflation is the reason this exists.
    """
    whole = int(abs(value))
    fraction = round(abs(value) - whole, 4)
    if not fraction:
        return number(whole if value >= 0 else -whole, gender)

    # Neither half is apocopated: the noun comes after the whole figure, so it
    # is "uno coma cuatro por ciento" and never "un coma cuatro".
    digits = f"{fraction:.10f}".split(".")[1].rstrip("0")
    said = f"{_bare(whole, gender)} coma {_bare(int(digits), gender)}"
    return f"menos {said}" if value < 0 else said


def _bare(value: int, gender: str) -> str:
    """The plain cardinal — "uno", not "un" — agreeing when it has to."""
    if abs(value) > MAXIMUM:
        raise ValueError(f"fuera de rango para decir en voz alta: {value}")
    word = _cardinal(abs(value))
    return _feminine(word) if gender == FEMININE else word


def _part_of_day(hour: int, minute: int) -> str:
    if hour == 12:
        return "del mediodía" if minute == 0 else "de la tarde"
    if hour == 0 or hour >= 20:
        return "de la noche"
    if hour <= 5:
        return "de la madrugada"
    if hour <= 11:
        return "de la mañana"
    return "de la tarde"


def _minutes(minute: int) -> str:
    if minute == 0:
        return ""
    if minute == 15:
        return " y cuarto"
    if minute == 30:
        return " y media"
    # "y uno" alone would dangle; the noun is what makes it a sentence.
    if minute == 1:
        return " y un minuto"
    return f" y {number(minute)}"


def clock(hour: int, minute: int = 0) -> str:
    """A time of day the way it is spoken: "las nueve y cuarto de la noche"."""
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        raise ValueError(f"no es una hora válida: {hour}:{minute}")

    shown = hour % 12 or 12
    article = "la" if shown == 1 else "las"
    return f"{article} {number(shown, FEMININE)}{_minutes(minute)} {_part_of_day(hour, minute)}"


# Every word this module can emit that carries a fact rather than style. A
# rewriter is allowed to move them around, never to add, drop or swap one:
# turning "de la mañana" into "de la tarde" moves an appointment by half a day.
# 🔴 "un" and "una" are deliberately absent. They are also the indefinite
# article, and a rewriter uses it constantly — "con una máxima de veinte" got
# read as two invented numbers and threw away a correct rewrite. Leaving them
# out costs nothing: a count that actually changes brings a different number
# word in or out ("una cosa" -> "dos cosas"), and that is still caught.
_FEMININE_FORMS = ("veintiuna",)
_APOCOPATED = ("veintiún",)
_PARTS_OF_DAY = ("madrugada", "mañana", "tarde", "noche", "mediodía")
_FRACTIONS = ("cuarto", "media")
# "mil" multiplies and "coma" splits: dropping either moves a figure by orders
# of magnitude. Money and inflation brought both into what the house says.
_MAGNITUDES = ("mil", "coma")

DATA_WORDS = frozenset(
    _UNITS
    + tuple(_TENS.values())
    + tuple(_HUNDREDS.values())
    + ("cien",)
    + tuple(word.replace("cientos", "cientas") for word in _HUNDREDS.values())
    + _FEMININE_FORMS
    + _APOCOPATED
    + _PARTS_OF_DAY
    + _FRACTIONS
    + _MAGNITUDES
    + ("menos",)
)


def data_words(text: str) -> Counter:
    """How many times each fact-carrying word appears, ignoring case and punctuation."""
    found = re.findall(r"[a-záéíóúüñ]+", text.lower())
    return Counter(word for word in found if word in DATA_WORDS)

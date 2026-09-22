"""Números y horas en palabras, para el sintetizador.

Piper lee un dígito como cardinal masculino suelto, así que todo lo que se vaya
a escuchar le llega ya deletreado y concordando con el sustantivo.
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

# El número más grande que este módulo puede decir en palabras.
MAXIMUM = 999_999


def _apocopate(word: str) -> str:
    """"veintiuno" -> "veintiún": la forma que toma un número antes de un sustantivo."""
    if word.endswith("veintiuno"):
        return f"{word[:-len('veintiuno')]}veintiún"
    if word.endswith("uno"):
        return f"{word[:-len('uno')]}un"
    return word


def _cardinal(value: int) -> str:
    """0-999999 en masculino llano, antes de aplicar cualquier concordancia."""
    if value >= 1000:
        thousands, rest = divmod(value, 1000)
        # "un mil" no existe, y el número antes de "mil" siempre va apocopado:
        # "veintiún mil", nunca "veintiuno mil".
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
    """Un número como se dice *antes de un sustantivo*: "un minuto", "veintiuna cosas".

    Es la única forma que este proyecto necesita —todo número que dice cuenta
    algo—, así que el masculino va apocopado.
    """
    if abs(value) > MAXIMUM:
        raise ValueError(f"fuera de rango para decir en voz alta: {value}")
    if value < 0:
        return f"menos {number(-value, gender)}"

    word = _cardinal(value)
    if gender == FEMININE:
        # Solo concuerda lo que viene después del último "mil": "mil
        # doscientas cosas", pero "veintiún mil".
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
    """Un número con decimales, como se lee: "dos coma uno".

    Escrito con coma, "2,1" le llega a Piper como dos números sueltos y se come
    el signo.
    """
    whole = int(abs(value))
    fraction = round(abs(value) - whole, 4)
    if not fraction:
        return number(whole if value >= 0 else -whole, gender)

    # Ninguna mitad se apocopa: el sustantivo va después de toda la cifra, así
    # que es "uno coma cuatro por ciento" y nunca "un coma cuatro".
    digits = f"{fraction:.10f}".split(".")[1].rstrip("0")
    said = f"{_bare(whole, gender)} coma {_bare(int(digits), gender)}"
    return f"menos {said}" if value < 0 else said


def _bare(value: int, gender: str) -> str:
    """El cardinal llano —"uno", no "un"— concordando cuando hace falta."""
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
    # "y uno" solo quedaría colgado; el sustantivo es lo que lo cierra.
    if minute == 1:
        return " y un minuto"
    return f" y {number(minute)}"


def clock(hour: int, minute: int = 0) -> str:
    """Una hora como se dice: "las nueve y cuarto de la noche"."""
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        raise ValueError(f"no es una hora válida: {hour}:{minute}")

    shown = hour % 12 or 12
    article = "la" if shown == 1 else "las"
    return f"{article} {number(shown, FEMININE)}{_minutes(minute)} {_part_of_day(hour, minute)}"


# Cada palabra que este módulo emite y que lleva un dato, no un estilo. Un
# reescritor puede moverlas, nunca agregar, sacar ni cambiar una. "un" y "una"
# quedan afuera a propósito: también son el artículo indefinido.
_FEMININE_FORMS = ("veintiuna",)
_APOCOPATED = ("veintiún",)
_PARTS_OF_DAY = ("madrugada", "mañana", "tarde", "noche", "mediodía")
_FRACTIONS = ("cuarto", "media")
# "mil" multiplica y "coma" parte: perder cualquiera de las dos mueve una
# cifra órdenes de magnitud.
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
    """Cuántas veces aparece cada palabra-dato, ignorando mayúsculas y puntuación."""
    found = re.findall(r"[a-záéíóúüñ]+", text.lower())
    return Counter(word for word in found if word in DATA_WORDS)

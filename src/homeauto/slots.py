"""Qué le falta a un comando para poder ejecutarse.

El router nombra el comando; esto dice si tiene con qué trabajar, así media
orden se vuelve una pregunta en vez del error del parser. Nunca completa nada:
el dato sale de la persona.

La forma de una alarma se mira acá y en `Commands.alarm`, y
`tests/bot/test_conversation.py` ata las dos mitades.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from homeauto.route import strip_target
from homeauto.timespec import TOMORROW_WORDS, TimeSpecError, parse_duration, parse_weekdays

# Las palabras que ya dicen cómo repite una alarma. `Commands.alarm` lee la
# misma tupla, así que una nueva se agrega en un solo lugar.
DAILY_WORDS = ("diaria", "diario", "daily")

_CLOCK = re.compile(r"\d{1,2}[:.]\d{2}")
_DIGIT = re.compile(r"\d")
# «en comedor» sin nada atrás: se nombró un equipo y el mensaje nunca llegó.
# `strip_target` no lo toca —solo saca un prefijo que tenga algo detrás—, así
# que acá cuenta como vacío.
_TARGET_ONLY = re.compile(r"^en\s+[a-z0-9_-]+(?:\s*,\s*[a-z0-9_-]+)*$", re.IGNORECASE)


@dataclass(frozen=True)
class Slot:
    """Un dato que falta: su nombre y con qué pregunta pedirlo.

    La pregunta va al chat y nunca al sintetizador, así que a diferencia de
    todo lo que la casa dice, puede llevar dígitos.
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
CALCULATION = Slot("cuenta", "¿Qué cuenta querés que haga?")
ITEM = Slot("item", "¿Qué agrego?")
POSITION = Slot("numero", "¿Cuál saco? El número sale en /compras.")
PHRASE = Slot("texto", "¿Qué traduzco?")


def missing(command: str, argument: str) -> Slot | None:
    """El primer dato que le falta al comando, o None si ya puede ejecutarse."""
    check = _CHECKS.get(command)
    return check(_payload(argument)) if check else None


def _payload(argument: str) -> str:
    """Lo que lleva el comando, sin el destino que va adelante."""
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
    """Si a un "<cuándo> <mensaje>" le falta alguna de sus dos mitades."""
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
        # Cómo repite ya está dicho; falta la hora y el texto.
        return _timed(tail, TIME)

    # Una alarma de una sola vez es una orden completa pero no obvia: se
    # pregunta en vez de agendarla en silencio.
    return _timed(argument, TIME) or REPEAT


def _removal(argument: str) -> Slot | None:
    """Sacar pide un número, salvo que se pida vaciar la lista entera."""
    if "todo" in argument.lower():
        return None
    return None if _DIGIT.search(argument) else POSITION


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
    "calcular": _needed(CALCULATION),
    "agregar": _needed(ITEM),
    "sacar": _removal,
    "traducir": _needed(PHRASE),
}

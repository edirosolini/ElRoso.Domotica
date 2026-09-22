"""Cuentas y conversiones, resueltas acá.

Un modelo contestaría lo mismo más lento y con dígitos, que es justo lo que el
sintetizador lee mal. Acá el número sale exacto y en palabras: `spoken` es lo
único que llega a Piper, `written` conserva la cifra para el chat.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass

from homeauto.verbalize import FEMININE, MASCULINE, decimal, number

# Tope del evaluador: sin él, "9 ** 9 ** 9" cuelga el proceso antes de contestar.
MAX_POWER_BASE = 1000
MAX_EXPONENT = 10
MAX_VALUE = 1e15
# Lo que se muestra escrito; más decimales que estos no los pidió nadie.
DECIMALS = 2


class CalcError(Exception):
    """No es una cuenta, o no se puede resolver."""


@dataclass(frozen=True)
class Result:
    """La cifra para el chat y su lectura en palabras, vacía si no se puede decir."""

    written: str
    spoken: str


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_SIGNS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

# Cómo se escribe una cuenta y cómo la escribe una persona.
_PREFIXES = (
    "cuánto es", "cuanto es", "cuánto son", "cuanto son", "cuánto da", "cuanto da",
    "cuántos son", "cuantos son", "calculá", "calcula", "calcular",
)
_WORD_OPERATORS = (
    (r"\belevado a\b", "**"),
    (r"\bdividido por\b", "/"),
    (r"\bdividido\b", "/"),
    (r"\bentre\b", "/"),
    (r"\bmultiplicado por\b", "*"),
    (r"\bmás\b", "+"),
    (r"\bmas\b", "+"),
    (r"\bmenos\b", "-"),
    (r"\bpor\b", "*"),
    (r"(?<=\d)\s*x\s*(?=\d)", "*"),
)
_PERCENTAGE = re.compile(
    r"^(-?\d+(?:[.,]\d+)?)\s*(?:%|por\s+ciento)\s+de\s+(-?\d+(?:[.,]\d+)?)$"
)
_CONVERSION = re.compile(
    r"^(-?\d+(?:[.,]\d+)?)\s*([a-záéíóúñ°]+(?:\s+[a-záéíóúñ°]+)?)\s+(?:en|a)\s+"
    r"([a-záéíóúñ°]+(?:\s+[a-záéíóúñ°]+)?)$"
)

# magnitud, factor a la base, símbolo, singular, plural, género, otros nombres.
_TABLE = (
    ("longitud", 1.0, "m", "metro", "metros", MASCULINE, ("mts",)),
    ("longitud", 1000.0, "km", "kilómetro", "kilómetros", MASCULINE, ("km", "kms", "kilometro", "kilometros")),
    ("longitud", 0.01, "cm", "centímetro", "centímetros", MASCULINE, ("cm", "centimetro", "centimetros")),
    ("longitud", 0.001, "mm", "milímetro", "milímetros", MASCULINE, ("mm",)),
    ("longitud", 1609.344, "mi", "milla", "millas", FEMININE, ("mi",)),
    ("longitud", 0.3048, "ft", "pie", "pies", MASCULINE, ("ft",)),
    ("longitud", 0.0254, "in", "pulgada", "pulgadas", FEMININE, ("in",)),
    ("longitud", 0.9144, "yd", "yarda", "yardas", FEMININE, ("yd",)),
    ("peso", 1.0, "g", "gramo", "gramos", MASCULINE, ("g", "gr")),
    ("peso", 1000.0, "kg", "kilo", "kilos", MASCULINE, ("kg", "kgs", "kilogramo", "kilogramos")),
    ("peso", 0.001, "mg", "miligramo", "miligramos", MASCULINE, ("mg",)),
    ("peso", 1_000_000.0, "t", "tonelada", "toneladas", FEMININE, ("t",)),
    ("peso", 453.59237, "lb", "libra", "libras", FEMININE, ("lb", "lbs")),
    ("peso", 28.349523125, "oz", "onza", "onzas", FEMININE, ("oz",)),
    ("volumen", 1.0, "l", "litro", "litros", MASCULINE, ("l", "lt", "lts")),
    ("volumen", 0.001, "ml", "mililitro", "mililitros", MASCULINE, ("ml", "cc")),
    ("volumen", 3.785411784, "gal", "galón", "galones", MASCULINE, ("gal", "galon")),
    ("volumen", 0.24, "taza", "taza", "tazas", FEMININE, ()),
)


@dataclass(frozen=True)
class Unit:
    magnitude: str
    factor: float
    symbol: str
    singular: str
    plural: str
    gender: str


def _units() -> dict[str, Unit]:
    known: dict[str, Unit] = {}
    for magnitude, factor, symbol, singular, plural, gender, extra in _TABLE:
        unit = Unit(magnitude, factor, symbol, singular, plural, gender)
        for name in (singular, plural, *extra):
            known[name] = unit
    return known


UNITS = _units()

# La temperatura no escala, se desplaza: va aparte, en grados Celsius de base.
_TEMPERATURES = {
    "celsius": ("°C", "Celsius", lambda c: c, lambda c: c),
    "fahrenheit": ("°F", "Fahrenheit", lambda f: (f - 32) * 5 / 9, lambda c: c * 9 / 5 + 32),
    "kelvin": ("K", "Kelvin", lambda k: k - 273.15, lambda c: c + 273.15),
}
# En esta casa se mide en Celsius: "veinte grados" no necesita apellido.
_TEMPERATURE_NAMES = {
    "grado": "celsius", "grados": "celsius", "celsius": "celsius",
    "centígrados": "celsius", "centigrados": "celsius", "c": "celsius",
    "grados celsius": "celsius", "grados centígrados": "celsius",
    "fahrenheit": "fahrenheit", "f": "fahrenheit", "grados fahrenheit": "fahrenheit",
    "kelvin": "kelvin", "k": "kelvin", "grados kelvin": "kelvin",
}


def evaluate(text: str) -> Result:
    """Resuelve una cuenta o una conversión, o explica por qué no puede."""
    clean = _clean(text)
    if not clean:
        raise CalcError("Pasame una cuenta: /calcular 15 por 4")

    conversion = _CONVERSION.match(clean)
    if conversion:
        return _convert(*conversion.groups())
    return _arithmetic(clean)


def _clean(text: str) -> str:
    clean = text.strip().lower().strip("¿?¡!.")
    for prefix in _PREFIXES:
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()
            break
    return clean.strip()


def _number(raw: str) -> float:
    return float(raw.replace(",", "."))


# --- aritmética -------------------------------------------------------------


def _arithmetic(clean: str) -> Result:
    percentage = _PERCENTAGE.match(clean)
    if percentage:
        part, whole = (_number(raw) for raw in percentage.groups())
        return _result(f"{_figure(part)}% de {_figure(whole)}", part * whole / 100)

    expression = _to_expression(clean)
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalcError(f"No entendí la cuenta: {clean}") from exc

    return _result(_pretty(expression), _eval(tree.body))


def _to_expression(clean: str) -> str:
    expression = clean
    for pattern, symbol in _WORD_OPERATORS:
        expression = re.sub(pattern, symbol, expression)
    # La coma decimal entre dígitos es nuestra; el punto es el de Python.
    return re.sub(r"(?<=\d),(?=\d)", ".", expression)


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return _guard(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SIGNS:
        return _guard(_SIGNS[type(node.op)](_eval(node.operand)))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow):
            _check_power(left, right)
        try:
            return _guard(_OPERATORS[type(node.op)](left, right))
        except ZeroDivisionError as exc:
            raise CalcError("No se puede dividir por cero.") from exc
        except (OverflowError, ValueError) as exc:
            raise CalcError("Ese número es demasiado grande.") from exc
    raise CalcError("Eso no es una cuenta.")


def _check_power(base, exponent) -> None:
    if abs(base) > MAX_POWER_BASE or abs(exponent) > MAX_EXPONENT:
        raise CalcError("Esa potencia es demasiado grande.")


def _guard(value):
    if isinstance(value, complex) or abs(value) > MAX_VALUE:
        raise CalcError("Ese número es demasiado grande.")
    return value


def _pretty(expression: str) -> str:
    """La cuenta como se lee, con la coma decimal de vuelta en su lugar."""
    shown = expression.replace("**", "^").replace("*", "×").replace("/", "÷")
    return re.sub(r"(?<=\d)\.(?=\d)", ",", shown)


# --- unidades ---------------------------------------------------------------


def _convert(raw: str, source: str, target: str) -> Result:
    value = _number(raw)
    source, target = source.strip(), target.strip()

    if source in _TEMPERATURE_NAMES or target in _TEMPERATURE_NAMES:
        return _convert_temperature(value, source, target)

    origin, destination = _unit(source), _unit(target)
    if origin.magnitude != destination.magnitude:
        raise CalcError(f"{origin.plural} y {destination.plural}: eso no se convierte.")

    result = value * origin.factor / destination.factor
    return _result(
        f"{_figure(value)} {_symbol(origin, value)}",
        result,
        separator="=",
        suffix=_symbol(destination, result),
        unit=destination,
    )


def _symbol(unit: Unit, value) -> str:
    """El símbolo, o el nombre en plural cuando la unidad no tiene abreviatura."""
    if unit.symbol != unit.singular:
        return unit.symbol
    return unit.singular if round(float(value), DECIMALS) == 1 else unit.plural


def _unit(name: str) -> Unit:
    try:
        return UNITS[name]
    except KeyError:
        raise CalcError(f"No conozco esa unidad: {name}") from None


def _convert_temperature(value: float, source: str, target: str) -> Result:
    origin, destination = _scale(source), _scale(target)
    symbol, spoken_name, to_celsius, _ = _TEMPERATURES[origin]
    target_symbol, target_name, _, from_celsius = _TEMPERATURES[destination]

    result = from_celsius(to_celsius(value))
    return Result(
        written=f"{_figure(value)} {symbol} = {_figure(result)} {target_symbol}",
        spoken=_say(result, f"grados {target_name}", f"grado {target_name}", MASCULINE),
    )


def _scale(name: str) -> str:
    try:
        return _TEMPERATURE_NAMES[name]
    except KeyError:
        raise CalcError(f"No conozco esa unidad: {name}") from None


# --- salida -----------------------------------------------------------------


def _result(left: str, value, separator: str = "=", suffix: str = "", unit: Unit | None = None) -> Result:
    written = f"{left} {separator} {_figure(value)}"
    if suffix:
        written = f"{written} {suffix}"

    if unit is None:
        return Result(written=written, spoken=_say(value, "", "", MASCULINE))
    return Result(written=written, spoken=_say(value, unit.plural, unit.singular, unit.gender))


def _figure(value) -> str:
    """La cifra como se escribe acá: punto para los miles, coma para el resto."""
    rounded = round(float(value), DECIMALS)
    if rounded == int(rounded):
        return f"{int(rounded):,}".replace(",", ".")
    whole, _, fraction = f"{rounded:,.{DECIMALS}f}".partition(".")
    return f"{whole.replace(',', '.')},{fraction.rstrip('0')}"


def _say(value, plural: str, singular: str, gender: str) -> str:
    """La lectura en palabras, o vacía si el número se sale del rango decible."""
    rounded = round(float(value), DECIMALS)
    one = rounded == 1
    try:
        spelled = number(int(rounded), gender) if rounded == int(rounded) else decimal(rounded)
    except ValueError:
        return ""

    noun = singular if one else plural
    verb = "Es" if one else "Son"
    return f"{verb} {spelled} {noun}.".replace("  ", " ").replace(" .", ".")

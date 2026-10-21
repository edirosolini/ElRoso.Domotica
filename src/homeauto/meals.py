"""El menú de la semana: lo arma un modelo, se valida y se guarda en `meal_plans`."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Iterable

from homeauto.correct import MEALS
from homeauto.quiet import away_of

log = logging.getLogger(__name__)

LUNCH = "almuerzo"
DINNER = "cena"
# Hora hasta la que cada comida sigue siendo la próxima.
LUNCH_ENDS = next(end for _start, end, name, _verb in MEALS if name == "el almuerzo")
DINNER_ENDS = 22
MEAL_ENDS = ((LUNCH, LUNCH_ENDS), (DINNER, DINNER_ENDS))

MENU_TIMEOUT = 30
KEEP_WEEKS = 8
MAX_DISH = 80
MAX_INGREDIENTS = 40
# Lo que hay en cualquier alacena: no va a la lista de compras.
PANTRY = ("sal", "aceite", "pimienta", "agua")

MENU_SHOP = "🛒 Pasar a compras"
MENU_OTHER = "🔄 Otra idea"

WEEK_PROMPT = """Armá el menú de una semana para una casa de Argentina, de lunes {first} a
domingo {last}.

Comidas de cada día: {meals}.
Platos caseros y variados, con ingredientes de un supermercado de Buenos Aires.
No repitas ninguno de estos platos: {avoid}.{request}

Reglas:
- Exactamente siete días, en orden de lunes a domingo.
- Cada plato con un nombre corto, de hasta {max_dish} caracteres.
- Los ingredientes sin cantidades, solo el nombre: "papas", no "1 kg de papas".
- No incluyas sal, aceite, pimienta, agua ni condimentos.

Contestá solo con JSON, así:
{example}"""

DISH_PROMPT = """Proponé {article} para el {weekday} {day} en una casa de Argentina.

Un plato casero, con ingredientes de un supermercado de Buenos Aires.
No repitas ninguno de estos platos: {avoid}.

Reglas:
- Un nombre corto, de hasta {max_dish} caracteres.
- Los ingredientes sin cantidades, solo el nombre: "papas", no "1 kg de papas".
- No incluyas sal, aceite, pimienta, agua ni condimentos.

Contestá solo con JSON, así:
{{"plato": "...", "ingredientes": ["...", "..."]}}"""

WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS meal_plans (
    day         DATE NOT NULL,
    meal        TEXT NOT NULL,
    dish        TEXT NOT NULL,
    ingredients TEXT NOT NULL,
    request     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    PRIMARY KEY (day, meal)
);
"""


class MealError(Exception):
    """No se pudo armar el menú."""


@dataclass(frozen=True)
class Meal:
    """Un plato de un día y una comida, con sus ingredientes."""

    day: date
    meal: str
    dish: str
    ingredients: tuple[str, ...]


def served(lunch_at: time | None, dinner_at: time | None) -> tuple[str, ...]:
    """Las comidas del menú, sin las que están en `off`."""
    return tuple(meal for meal, at in ((LUNCH, lunch_at), (DINNER, dinner_at)) if at is not None)


def upcoming(now: datetime, meals: Iterable[str]) -> tuple[date, str] | None:
    """El día y la comida que vienen, o None si no hay comidas."""
    meals = tuple(meals)
    for offset in (0, 1):
        day = now.date() + timedelta(days=offset)
        for meal, end in MEAL_ENDS:
            if meal in meals and (offset or now.hour < end):
                return day, meal
    return None


def left_today(now: datetime, meals: Iterable[str]) -> tuple[str, ...]:
    """Las comidas de hoy que todavía no pasaron."""
    return tuple(meal for meal, end in MEAL_ENDS if meal in meals and now.hour < end)


def week_of(day: date) -> date:
    """El lunes de la semana de `day`."""
    return day - timedelta(days=day.weekday())


def _fold(text: str) -> str:
    """En minúsculas y sin acentos, para comparar."""
    plain = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in plain if not unicodedata.combining(c))


def _is_pantry(item: str) -> bool:
    words = _fold(item).split()
    return bool(words) and (words[0] in PANTRY or "condimento" in _fold(item))


def _parse_json(reply: str):
    text = (reply or "").strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise MealError("lo que volvió no se pudo leer.") from exc


def _dish(raw, day: date, meal: str) -> Meal:
    """Un plato validado, sin lo de la alacena; `MealError` si no sirve."""
    which = f"{'la' if meal == DINNER else 'el'} {meal} del {day:%d/%m}"
    if not isinstance(raw, dict):
        raise MealError(f"falta {which}.")
    dish = raw.get("plato")
    if not isinstance(dish, str) or not dish.strip() or len(dish.strip()) > MAX_DISH:
        raise MealError(f"{which} vino sin un nombre de plato usable.")
    items = raw.get("ingredientes")
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        raise MealError(f"{which} vino sin ingredientes.")
    kept: list[str] = []
    for item in (i.strip() for i in items):
        if any(c.isdigit() for c in item):
            raise MealError(f"«{item}» trae cantidades.")
        if item and not _is_pantry(item) and _fold(item) not in map(_fold, kept):
            kept.append(item)
    if not 1 <= len(kept) <= MAX_INGREDIENTS:
        raise MealError(f"{which} no tiene entre uno y {MAX_INGREDIENTS} ingredientes.")
    return Meal(day, meal, dish.strip(), tuple(kept))


def _avoided(avoid: Iterable[str]) -> str:
    dishes = [dish for dish in avoid if dish]
    return "; ".join(dishes) if dishes else "ninguno"


class MealPlanner:
    """Pide el menú al modelo y lo devuelve validado."""

    def __init__(self, model: Callable[[str], str]):
        self.model = model

    def plan(
        self, start: date, meals: tuple[str, ...], request: str = "", avoid: Iterable[str] = ()
    ) -> list[Meal]:
        """La semana desde el lunes `start`, en orden; `MealError` si no sirve entera."""
        example = json.dumps(
            {"dias": [{meal: {"plato": "...", "ingredientes": ["...", "..."]} for meal in meals}]},
            ensure_ascii=False,
        )
        prompt = WEEK_PROMPT.format(
            first=f"{start:%d/%m}",
            last=f"{start + timedelta(days=6):%d/%m}",
            meals=" y ".join(meals),
            avoid=_avoided(avoid),
            request=f"\nPedido de la casa: {request.strip()}" if request.strip() else "",
            max_dish=MAX_DISH,
            example=example,
        )
        answer = self._ask(prompt)
        days = answer.get("dias") if isinstance(answer, dict) else None
        if not isinstance(days, list) or len(days) != 7:
            raise MealError("no vinieron los siete días.")
        week = []
        for offset, raw in enumerate(days):
            day = start + timedelta(days=offset)
            if not isinstance(raw, dict):
                raise MealError(f"el {day:%d/%m} vino vacío.")
            week += [_dish(raw.get(meal), day, meal) for meal in meals]
        return week

    def another(self, day: date, meal: str, avoid: Iterable[str] = ()) -> Meal:
        """Otro plato para ese día y esa comida; `MealError` si no sirve."""
        prompt = DISH_PROMPT.format(
            article="un almuerzo" if meal == LUNCH else "una cena",
            weekday=WEEKDAYS[day.weekday()],
            day=f"{day:%d/%m}",
            avoid=_avoided(avoid),
            max_dish=MAX_DISH,
        )
        return _dish(self._ask(prompt), day, meal)

    def _ask(self, prompt: str):
        try:
            reply = self.model(prompt)
        except Exception as exc:  # noqa: BLE001
            raise MealError(f"el modelo no contestó ({exc}).") from exc
        return _parse_json(reply)


class MealStore:
    """Un plato por día y comida: la tabla diecinueve de `jobs.db`, dueña de su esquema."""

    def __init__(self, db_path: Path | str, clock: Callable[[], datetime] = datetime.now):
        self.db_path = Path(db_path)
        self.clock = clock
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def week(self, start: date) -> list[Meal]:
        """Los platos de la semana del lunes `start`, por día y almuerzo antes que cena."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM meal_plans WHERE day >= ? AND day < ?"
                " ORDER BY day, CASE meal WHEN ? THEN 0 ELSE 1 END",
                (start.isoformat(), (start + timedelta(days=7)).isoformat(), LUNCH),
            ).fetchall()
        return [_meal(row) for row in rows]

    def request(self, start: date) -> str:
        """El pedido con que se armó esa semana, o vacío."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT request FROM meal_plans WHERE day >= ? AND day < ? LIMIT 1",
                (start.isoformat(), (start + timedelta(days=7)).isoformat()),
            ).fetchone()
        return row["request"] if row else ""

    def get(self, day: date, meal: str) -> Meal | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meal_plans WHERE day = ? AND meal = ?", (day.isoformat(), meal)
            ).fetchone()
        return _meal(row) if row else None

    def save_week(self, start: date, meals: list[Meal], request: str = "") -> None:
        """Reemplaza la semana entera de una vez y poda lo de más de `KEEP_WEEKS` atrás."""
        created = self.clock().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM meal_plans WHERE day >= ? AND day < ?",
                (start.isoformat(), (start + timedelta(days=7)).isoformat()),
            )
            conn.executemany(
                "INSERT INTO meal_plans (day, meal, dish, ingredients, request, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (m.day.isoformat(), m.meal, m.dish, _dump(m.ingredients), request, created)
                    for m in meals
                ],
            )
            conn.execute(
                "DELETE FROM meal_plans WHERE day < ?",
                ((start - timedelta(weeks=KEEP_WEEKS)).isoformat(),),
            )

    def replace(self, meal: Meal) -> None:
        """Cambia un plato, conservando el pedido de su semana."""
        request = self.request(week_of(meal.day))
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO meal_plans"
                " (day, meal, dish, ingredients, request, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    meal.day.isoformat(), meal.meal, meal.dish, _dump(meal.ingredients),
                    request, self.clock().isoformat(timespec="seconds"),
                ),
            )


class MealReminder:
    """El aviso escrito antes de cada comida, con el plato del menú y sus botones."""

    def __init__(
        self,
        store: MealStore,
        planner: MealPlanner,
        meals: tuple[str, ...],
        quiet=None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.store = store
        self.planner = planner
        self.meals = meals
        self.quiet = quiet
        self.clock = clock

    def text_for(
        self, now: datetime, meal: str
    ) -> tuple[str, tuple[tuple[str, str], ...]] | None:
        """El aviso de esa comida de hoy y sus botones, o None si no hay nada que mandar."""
        if meal not in self.meals or (self.quiet is not None and away_of(self.quiet, now)):
            return None
        today = now.date()
        dish = self.store.get(today, meal)
        if dish is None and self._plan_week(week_of(today)):
            dish = self.store.get(today, meal)
        if dish is None:
            return None
        text = (
            f"🍽 Idea para {'la' if meal == DINNER else 'el'} {meal}: {dish.dish}.\n"
            f"Lleva: {', '.join(dish.ingredients)}."
        )
        actions = (
            (MENU_SHOP, f"menu compras {today.isoformat()} {meal}"),
            (MENU_OTHER, f"menu otra {today.isoformat()} {meal}"),
        )
        return text, actions

    def _plan_week(self, start: date) -> bool:
        """Arma y guarda la semana si falta y hubo menú la anterior; True si la armó."""
        if self.store.week(start):
            return False
        last = self.store.week(start - timedelta(days=7))
        if not last:
            return False
        try:
            week = self.planner.plan(start, self.meals, avoid=[m.dish for m in last])
        except MealError as exc:
            log.warning("no pude armar el menú para el aviso: %s", exc)
            return False
        self.store.save_week(start, week)
        return True


def _dump(ingredients: tuple[str, ...]) -> str:
    return json.dumps(list(ingredients), ensure_ascii=False)


def _meal(row: sqlite3.Row) -> Meal:
    return Meal(
        date.fromisoformat(row["day"]),
        row["meal"],
        row["dish"],
        tuple(json.loads(row["ingredients"])),
    )

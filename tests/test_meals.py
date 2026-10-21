"""El menú de la semana: qué se pide al modelo, qué se acepta y qué se guarda."""

import json
import sqlite3
from datetime import date, datetime, timedelta

import pytest

from homeauto import correct
from homeauto.meals import (
    DINNER,
    DINNER_ENDS,
    KEEP_WEEKS,
    LUNCH,
    LUNCH_ENDS,
    Meal,
    MealError,
    MealPlanner,
    MealReminder,
    MealStore,
    left_today,
    served,
    upcoming,
)

MONDAY = date(2026, 10, 19)
BOTH = (LUNCH, DINNER)


def week_json(days=7, meals=BOTH, dish="Milanesas con puré {i}", ingredients=None, fence=False):
    """Una semana como la devolvería el modelo."""
    body = {
        "dias": [
            {
                meal: {
                    "plato": dish.format(i=f"{i}{meal[0]}"),
                    "ingredientes": ingredients or ["carne", "papas", "pan rallado"],
                }
                for meal in meals
            }
            for i in range(days)
        ]
    }
    raw = json.dumps(body, ensure_ascii=False)
    return f"```json\n{raw}\n```" if fence else raw


def model_saying(reply):
    def model(prompt):
        model.prompts.append(prompt)
        return reply
    model.prompts = []
    return model


# --- upcoming -------------------------------------------------------------


def test_the_lunch_ends_where_correct_says():
    assert LUNCH_ENDS == next(end for _s, end, name, _v in correct.MEALS if name == "el almuerzo")
    assert LUNCH_ENDS == 15
    assert DINNER_ENDS == 22


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (8, 0, (MONDAY, LUNCH)),
        (14, 59, (MONDAY, LUNCH)),
        (15, 0, (MONDAY, DINNER)),
        (21, 59, (MONDAY, DINNER)),
        (22, 0, (MONDAY + timedelta(days=1), LUNCH)),
        (23, 30, (MONDAY + timedelta(days=1), LUNCH)),
    ],
)
def test_upcoming_follows_the_clock(hour, minute, expected):
    now = datetime.combine(MONDAY, datetime.min.time()).replace(hour=hour, minute=minute)

    assert upcoming(now, BOTH) == expected


def test_without_lunch_the_next_is_dinner_until_ten():
    now = datetime(2026, 10, 19, 9, 0)

    assert upcoming(now, (DINNER,)) == (MONDAY, DINNER)
    assert upcoming(now.replace(hour=22), (DINNER,)) == (MONDAY + timedelta(days=1), DINNER)


def test_without_dinner_the_lunch_after_three_is_tomorrow():
    now = datetime(2026, 10, 19, 16, 0)

    assert upcoming(now, (LUNCH,)) == (MONDAY + timedelta(days=1), LUNCH)


def test_without_meals_there_is_nothing_upcoming():
    assert upcoming(datetime(2026, 10, 19, 12, 0), ()) is None


def test_what_is_left_of_today_follows_the_same_clock():
    assert left_today(datetime(2026, 10, 19, 14, 59), BOTH) == BOTH
    assert left_today(datetime(2026, 10, 19, 15, 0), BOTH) == (DINNER,)
    assert left_today(datetime(2026, 10, 19, 22, 0), BOTH) == ()
    assert left_today(datetime(2026, 10, 19, 9, 0), (DINNER,)) == (DINNER,)


def test_served_drops_the_meals_turned_off():
    from datetime import time

    assert served(time(11), time(17, 30)) == BOTH
    assert served(None, time(17, 30)) == (DINNER,)
    assert served(time(11), None) == (LUNCH,)
    assert served(None, None) == ()


# --- el planificador --------------------------------------------------------


def test_a_week_has_seven_days_from_monday_with_each_meal():
    planner = MealPlanner(model_saying(week_json()))

    week = planner.plan(MONDAY, BOTH)

    assert len(week) == 14
    assert [m.day for m in week[::2]] == [MONDAY + timedelta(days=i) for i in range(7)]
    assert {m.meal for m in week} == set(BOTH)
    assert week[0] == Meal(MONDAY, LUNCH, "Milanesas con puré 0a", ("carne", "papas", "pan rallado"))


def test_the_json_fence_is_accepted():
    planner = MealPlanner(model_saying(week_json(fence=True)))

    assert len(planner.plan(MONDAY, BOTH)) == 14


def test_only_the_configured_meals_are_asked_and_kept():
    model = model_saying(week_json(meals=(DINNER,)))

    week = MealPlanner(model).plan(MONDAY, (DINNER,))

    assert {m.meal for m in week} == {DINNER}
    assert "Comidas de cada día: cena." in model.prompts[0]


def test_the_request_travels_in_the_prompt():
    model = model_saying(week_json())

    MealPlanner(model).plan(MONDAY, BOTH, request="sin carne el viernes")

    assert "sin carne el viernes" in model.prompts[0]


def test_last_weeks_dishes_travel_in_the_prompt():
    model = model_saying(week_json())

    MealPlanner(model).plan(MONDAY, BOTH, avoid=["Guiso de lentejas"])

    assert "Guiso de lentejas" in model.prompts[0]


def test_the_prompt_asks_for_ingredients_without_quantities_nor_pantry():
    model = model_saying(week_json())

    MealPlanner(model).plan(MONDAY, BOTH)

    prompt = model.prompts[0]
    assert "sin cantidades" in prompt
    for pantry in ("sal", "aceite", "pimienta", "agua", "condimentos"):
        assert pantry in prompt


def test_the_pantry_is_dropped_in_code():
    planner = MealPlanner(model_saying(week_json(
        ingredients=["Sal", "aceite de oliva", "pimienta negra", "agua", "condimentos",
                     "papas", "salsa de tomate", "aceitunas", "pimiento"],
    )))

    week = planner.plan(MONDAY, BOTH)

    assert week[0].ingredients == ("papas", "salsa de tomate", "aceitunas", "pimiento")


@pytest.mark.parametrize(
    "reply",
    [
        "no sé",
        week_json(days=6),
        week_json(days=8),
        week_json(meals=(LUNCH,)),
        week_json(dish=""),
        week_json(dish="x" * 81),
        week_json(ingredients=["2 kg de papas"]),
        week_json(ingredients=["sal", "aceite"]),
        week_json(ingredients=[f"cosa {chr(97 + i)}{chr(97 + j)}" for i in range(7) for j in range(6)]),
        json.dumps({"dias": "nada"}),
        json.dumps([1, 2]),
    ],
)
def test_an_invalid_week_is_refused(reply):
    with pytest.raises(MealError):
        MealPlanner(model_saying(reply)).plan(MONDAY, BOTH)


def test_a_model_that_fails_is_a_meal_error():
    def broken(_prompt):
        raise TimeoutError("lento")

    with pytest.raises(MealError):
        MealPlanner(broken).plan(MONDAY, BOTH)


def test_another_dish_avoids_what_is_already_planned():
    model = model_saying(json.dumps({"plato": "Tarta de acelga", "ingredientes": ["acelga", "huevos", "sal"]}))

    meal = MealPlanner(model).another(MONDAY, DINNER, avoid=["Milanesas con puré"])

    assert meal == Meal(MONDAY, DINNER, "Tarta de acelga", ("acelga", "huevos"))
    assert "Milanesas con puré" in model.prompts[0]
    assert "cena" in model.prompts[0]


def test_another_dish_that_comes_back_invalid_is_refused():
    with pytest.raises(MealError):
        MealPlanner(model_saying(json.dumps({"plato": "", "ingredientes": ["acelga"]}))).another(
            MONDAY, DINNER
        )


# --- la tabla ---------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    return MealStore(tmp_path / "jobs.db")


def a_week(start=MONDAY, dish="Plato"):
    return [
        Meal(start + timedelta(days=i), meal, f"{dish} {i} {meal}", ("papas",))
        for i in range(7)
        for meal in BOTH
    ]


def test_the_table_is_meal_plans_with_day_and_meal_as_key(store):
    with sqlite3.connect(store.db_path) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(meal_plans)")}

    assert set(columns) == {"day", "meal", "dish", "ingredients", "request", "created_at"}
    assert columns["day"][5] == 1 and columns["meal"][5] == 2


def test_a_saved_week_comes_back_in_order(store):
    store.save_week(MONDAY, a_week(), request="sin carne")

    week = store.week(MONDAY)

    assert week == a_week()
    assert store.request(MONDAY) == "sin carne"


def test_saving_a_week_again_replaces_it(store):
    store.save_week(MONDAY, a_week(dish="Viejo"))
    store.save_week(MONDAY, a_week(dish="Nuevo")[:2])

    assert [m.dish for m in store.week(MONDAY)] == ["Nuevo 0 almuerzo", "Nuevo 0 cena"]


def test_the_ingredients_are_stored_as_json(store):
    store.save_week(MONDAY, a_week())

    with sqlite3.connect(store.db_path) as conn:
        raw = conn.execute("SELECT ingredients FROM meal_plans LIMIT 1").fetchone()[0]

    assert json.loads(raw) == ["papas"]


def test_one_meal_is_read_and_replaced(store):
    store.save_week(MONDAY, a_week())

    store.replace(Meal(MONDAY, DINNER, "Tarta", ("acelga",)))

    assert store.get(MONDAY, DINNER) == Meal(MONDAY, DINNER, "Tarta", ("acelga",))
    assert store.get(MONDAY + timedelta(days=30), DINNER) is None


def test_more_than_eight_weeks_back_is_pruned(store):
    old = MONDAY - timedelta(weeks=KEEP_WEEKS + 1)
    kept = MONDAY - timedelta(weeks=KEEP_WEEKS)
    store.save_week(old, a_week(old))
    store.save_week(kept, a_week(kept))

    store.save_week(MONDAY, a_week())

    assert store.week(old) == []
    assert store.week(kept) != []


def test_a_broken_insert_saves_nothing(store):
    store.save_week(MONDAY, a_week(dish="Bueno"))
    broken = a_week(dish="Malo")
    broken.append(broken[0])

    with pytest.raises(sqlite3.IntegrityError):
        store.save_week(MONDAY, broken)

    assert store.week(MONDAY)[0].dish == "Bueno 0 almuerzo"


# --- el aviso antes de cada comida -------------------------------------------

TUESDAY_LUNCH = datetime(2026, 10, 20, 11, 0)


class Away:
    """Un silencio con la forma de `Hush`, de vacaciones o no."""

    def __init__(self, away=False):
        self.away = away

    def is_away(self, moment=None):
        return self.away

    def is_quiet(self, moment):
        return True


def reminder(store, model=None, quiet=None, meals=BOTH):
    model = model or model_saying(week_json(dish="Nuevo {i}"))
    return MealReminder(
        store=store, planner=MealPlanner(model), quiet=quiet, meals=meals,
        clock=lambda: TUESDAY_LUNCH,
    )


def test_the_reminder_writes_the_dish_and_what_it_takes(store):
    store.save_week(MONDAY, a_week())
    store.replace(Meal(MONDAY + timedelta(days=1), LUNCH, "Milanesas con puré",
                       ("carne", "pan rallado", "huevo", "papa")))

    text, actions = reminder(store).text_for(TUESDAY_LUNCH, LUNCH)

    assert text == (
        "🍽 Idea para el almuerzo: Milanesas con puré.\n"
        "Lleva: carne, pan rallado, huevo, papa."
    )
    assert actions == (
        ("🛒 Pasar a compras", "menu compras 2026-10-20 almuerzo"),
        ("🔄 Otra idea", "menu otra 2026-10-20 almuerzo"),
    )


def test_the_dinner_reminder_says_la_cena(store):
    store.save_week(MONDAY, a_week())

    text, actions = reminder(store).text_for(TUESDAY_LUNCH.replace(hour=17, minute=30), DINNER)

    assert text.startswith("🍽 Idea para la cena: Plato 1 cena.\n")
    assert actions[1] == ("🔄 Otra idea", "menu otra 2026-10-20 cena")


def test_the_buttons_fit_in_telegram(store):
    store.save_week(MONDAY, a_week())

    _text, actions = reminder(store).text_for(TUESDAY_LUNCH, LUNCH)

    assert all(len(data.encode("utf-8")) <= 64 for _label, data in actions)


def test_without_this_week_it_plans_it_avoiding_last_week(store):
    last = MONDAY - timedelta(days=7)
    store.save_week(last, a_week(last, dish="Viejo"))
    model = model_saying(week_json(dish="Nuevo {i}"))

    text, _actions = reminder(store, model=model).text_for(TUESDAY_LUNCH, LUNCH)

    assert "Nuevo 1a" in text
    assert "Viejo 0 almuerzo" in model.prompts[0]
    assert len(store.week(MONDAY)) == 14


def test_without_any_menu_it_writes_nothing(store):
    model = model_saying(week_json())

    assert reminder(store, model=model).text_for(TUESDAY_LUNCH, LUNCH) is None
    assert model.prompts == []
    assert store.week(MONDAY) == []


def test_on_vacation_it_writes_nothing(store):
    store.save_week(MONDAY, a_week())

    assert reminder(store, quiet=Away(away=True)).text_for(TUESDAY_LUNCH, LUNCH) is None


def test_quiet_hours_do_not_stop_it_because_it_is_only_written(store):
    store.save_week(MONDAY, a_week())

    assert reminder(store, quiet=Away(away=False)).text_for(TUESDAY_LUNCH, LUNCH) is not None


def test_a_model_that_fails_writes_nothing_and_saves_nothing(store, caplog):
    last = MONDAY - timedelta(days=7)
    store.save_week(last, a_week(last))

    def broken(prompt):
        raise TimeoutError("sin respuesta")

    assert reminder(store, model=broken).text_for(TUESDAY_LUNCH, LUNCH) is None
    assert store.week(MONDAY) == []
    assert "menú" in caplog.text


def test_a_meal_missing_from_a_saved_week_writes_nothing(store):
    store.save_week(MONDAY, [m for m in a_week() if m.meal == DINNER])
    model = model_saying(week_json())

    assert reminder(store, model=model).text_for(TUESDAY_LUNCH, LUNCH) is None
    assert model.prompts == []

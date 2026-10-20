"""`/menu`: la semana de comidas, escrita, y sus ingredientes a la lista de compras."""

import json
from datetime import date, datetime, time

import pytest

from homeauto.bot.commands import Commands, with_actions
from homeauto.lists import SHOPPING, ListStore
from homeauto.meals import DINNER, LUNCH, Meal, MealPlanner, MealStore

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
OTHER = 77
TUESDAY = datetime(2026, 10, 20, 10, 0)
MONDAY = date(2026, 10, 19)


class WeekModel:
    """Contesta como el modelo: una semana en JSON, o un plato si se pide uno."""

    def __init__(self, prefix="Plato", reply=None):
        self.prefix = prefix
        self.reply = reply
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if self.reply is not None:
            return self.reply
        if '"dias"' in prompt:
            meals = [m for m in (LUNCH, DINNER) if f'"{m}"' in prompt.split("Contestá")[1]]
            days = [
                {meal: {"plato": f"{self.prefix} {i} {meal}", "ingredientes": [f"cosa {'abcdefg'[i]} {meal}", "pan", "sal"]}
                 for meal in meals}
                for i in range(7)
            ]
            return "```json\n" + json.dumps({"dias": days}, ensure_ascii=False) + "\n```"
        return json.dumps({"plato": "Tarta de acelga", "ingredientes": ["acelga", "huevos", "aceite"]})


class Told:
    def __init__(self):
        self.messages = []

    def __call__(self, chat_id, text):
        self.messages.append((chat_id, text))


def build(tmp_path, model=None, clock=TUESDAY, planner=True, **config):
    model = model or WeekModel()
    told = Told()
    speakers = {"parlante": FakeSpeaker("parlante")}
    cmd = Commands(
        config=make_config(allowed={OWNER, OTHER}, **config),
        speakers=StubRegistry(**speakers),
        lists=ListStore(tmp_path / "jobs.db"),
        meal_store=MealStore(tmp_path / "jobs.db"),
        meal_planner=MealPlanner(model) if planner else None,
        tell_others=told,
        clock=lambda: clock,
    )
    return cmd, model, told, speakers


def run(cmd, text, who=""):
    return with_actions(cmd.menu, OWNER, text, who=who)


# --- ver la semana ----------------------------------------------------------


def test_the_first_menu_is_made_and_saved(tmp_path):
    cmd, model, _, _ = build(tmp_path)

    reply = run(cmd, "")

    assert len(model.prompts) == 1
    assert len(cmd.meal_store.week(MONDAY)) == 14
    assert "Plato 0 almuerzo" in reply.text and "Plato 6 cena" in reply.text
    assert "19/10" in reply.text and "25/10" in reply.text


def test_today_is_marked(tmp_path):
    cmd, _, _, _ = build(tmp_path)

    lines = run(cmd, "").text.splitlines()

    marked = [line for line in lines if "hoy" in line]
    assert len(marked) == 1
    assert "20/10" in marked[0]


def test_a_saved_menu_is_not_asked_again(tmp_path):
    cmd, model, _, _ = build(tmp_path)
    run(cmd, "")

    run(cmd, "")

    assert len(model.prompts) == 1


def test_on_sunday_the_next_week_is_made(tmp_path):
    cmd, model, _, _ = build(tmp_path, clock=datetime(2026, 10, 25, 12, 0))

    reply = run(cmd, "")

    assert len(cmd.meal_store.week(date(2026, 10, 26))) == 14
    assert "26/10" in reply.text and "01/11" in reply.text
    assert "26/10" in model.prompts[0]


def test_last_weeks_dishes_are_not_repeated(tmp_path):
    cmd, model, _, _ = build(tmp_path)
    cmd.meal_store.save_week(date(2026, 10, 12), [Meal(date(2026, 10, 12), LUNCH, "Guiso", ("lentejas",))])

    run(cmd, "")

    assert "Guiso" in model.prompts[0]


def test_the_week_offers_shopping_and_another_idea_for_what_comes(tmp_path):
    cmd, _, _, _ = build(tmp_path)

    actions = dict((data, label) for label, data in run(cmd, "").actions)

    assert actions["menu compras semana"] == "🛒 Pasar a compras"
    assert actions["menu otra 2026-10-20 almuerzo"].startswith("🔄 Otra idea")


def test_every_button_fits_in_a_telegram_callback(tmp_path):
    cmd, _, _, _ = build(tmp_path)
    run(cmd, "")

    for text in ("", "otra 2026-10-21 almuerzo"):
        for _label, data in run(cmd, text).actions:
            assert len(data.encode("utf-8")) <= 64, data


def test_only_dinner_when_lunch_is_off(tmp_path):
    cmd, model, _, _ = build(tmp_path, menu_lunch_at=None)

    reply = run(cmd, "")

    assert {m.meal for m in cmd.meal_store.week(MONDAY)} == {DINNER}
    assert "almuerzo" not in reply.text.lower()


def test_with_both_meals_off_it_says_so(tmp_path):
    cmd, model, _, _ = build(tmp_path, menu_lunch_at=None, menu_dinner_at=None)

    reply = run(cmd, "")

    assert "MENU_LUNCH_AT" in reply.text and "MENU_DINNER_AT" in reply.text
    assert model.prompts == []


def test_without_a_planner_it_asks_for_the_model(tmp_path):
    cmd, _, _, _ = build(tmp_path, planner=False)

    reply = run(cmd, "")

    assert "LLM_API_KEY" in reply.text


def test_a_menu_that_comes_back_broken_saves_nothing(tmp_path):
    cmd, _, _, _ = build(tmp_path, model=WeekModel(reply="no sé"))

    reply = run(cmd, "")

    assert "menú" in reply.text.lower()
    assert cmd.meal_store.week(MONDAY) == []


def test_it_never_reaches_the_speaker(tmp_path):
    cmd, _, _, speakers = build(tmp_path)

    reply = run(cmd, "por el parlante")

    assert speakers["parlante"].said == []
    assert "Plato 0 almuerzo" in reply.text
    assert "no lo digo" in reply.text.lower()


def test_an_unknown_form_says_how_to_use_it(tmp_path):
    cmd, _, _, _ = build(tmp_path)

    reply = run(cmd, "bailar")

    assert "/menu nuevo" in reply.text and "/menu compras" in reply.text


# --- volver a armarla -------------------------------------------------------


def test_new_makes_it_again_with_the_request(tmp_path):
    model = WeekModel(prefix="Viejo")
    cmd, _, _, _ = build(tmp_path, model=model)
    run(cmd, "")
    model.prefix = "Nuevo"

    reply = run(cmd, "nuevo sin carne el viernes")

    assert "sin carne el viernes" in model.prompts[-1]
    assert cmd.meal_store.week(MONDAY)[0].dish == "Nuevo 0 almuerzo"
    assert cmd.meal_store.request(MONDAY) == "sin carne el viernes"
    assert "Nuevo 0 almuerzo" in reply.text


def test_new_without_a_request_also_works(tmp_path):
    cmd, model, _, _ = build(tmp_path)
    run(cmd, "")

    run(cmd, "nuevo")

    assert len(model.prompts) == 2


def test_a_broken_new_menu_keeps_the_old_one(tmp_path):
    model = WeekModel()
    cmd, _, _, _ = build(tmp_path, model=model)
    run(cmd, "")
    model.reply = "no sé"

    run(cmd, "nuevo")

    assert cmd.meal_store.week(MONDAY)[0].dish == "Plato 0 almuerzo"


# --- a la lista de compras ----------------------------------------------------


def test_shopping_passes_what_is_left_of_today(tmp_path):
    cmd, _, _, _ = build(tmp_path, clock=datetime(2026, 10, 20, 16, 0))
    run(cmd, "")

    reply = run(cmd, "compras")

    assert cmd.lists.items(SHOPPING) == ["cosa b cena", "pan"]
    assert "cosa b cena" in reply.text


def test_shopping_in_the_morning_takes_both_meals_of_today(tmp_path):
    cmd, _, _, _ = build(tmp_path)
    run(cmd, "")

    run(cmd, "compras")

    assert cmd.lists.items(SHOPPING) == ["cosa b almuerzo", "pan", "cosa b cena"]


def test_shopping_for_the_week_takes_everything_once(tmp_path):
    cmd, _, _, _ = build(tmp_path)
    run(cmd, "")

    reply = run(cmd, "compras semana")

    items = cmd.lists.items(SHOPPING)
    assert len(items) == 15
    assert items.count("pan") == 1
    assert "Agregado a compras" in reply.text


def test_shopping_for_one_meal(tmp_path):
    cmd, _, _, _ = build(tmp_path)
    run(cmd, "")

    run(cmd, "compras 2026-10-22 cena")

    assert cmd.lists.items(SHOPPING) == ["cosa d cena", "pan"]


def test_what_was_already_on_the_list_is_said(tmp_path):
    cmd, _, _, _ = build(tmp_path)
    run(cmd, "")
    cmd.lists.add(SHOPPING, ["pan"])

    reply = run(cmd, "compras 2026-10-22 cena")

    assert "Ya estaba en compras: pan" in reply.text


def test_shopping_without_a_menu_says_how_to_make_one(tmp_path):
    cmd, model, _, _ = build(tmp_path)

    reply = run(cmd, "compras")

    assert "/menu" in reply.text
    assert cmd.lists.items(SHOPPING) == []
    assert model.prompts == []


def test_shopping_late_at_night_has_nothing_left_of_today(tmp_path):
    cmd, _, _, _ = build(tmp_path, clock=datetime(2026, 10, 20, 23, 0))
    run(cmd, "")

    reply = run(cmd, "compras")

    assert cmd.lists.items(SHOPPING) == []
    assert "/menu compras semana" in reply.text


def test_shopping_for_a_meal_that_is_not_there(tmp_path):
    cmd, _, _, _ = build(tmp_path)
    run(cmd, "")

    reply = run(cmd, "compras 2026-12-01 cena")

    assert cmd.lists.items(SHOPPING) == []
    assert "No hay" in reply.text


# --- otra idea --------------------------------------------------------------


def test_another_idea_changes_that_dish_only(tmp_path):
    cmd, model, _, _ = build(tmp_path)
    run(cmd, "")

    reply = run(cmd, "otra 2026-10-21 cena")

    assert cmd.meal_store.get(date(2026, 10, 21), DINNER).dish == "Tarta de acelga"
    assert cmd.meal_store.get(date(2026, 10, 21), DINNER).ingredients == ("acelga", "huevos")
    assert cmd.meal_store.get(date(2026, 10, 21), LUNCH).dish == "Plato 2 almuerzo"
    assert "Tarta de acelga" in reply.text
    assert "Plato 2 cena" in model.prompts[-1]


def test_another_idea_offers_its_shopping_and_one_more(tmp_path):
    cmd, _, _, _ = build(tmp_path)
    run(cmd, "")

    actions = run(cmd, "otra 2026-10-21 cena").actions

    assert ("🛒 Pasar a compras", "menu compras 2026-10-21 cena") in actions
    assert ("🔄 Otra idea", "menu otra 2026-10-21 cena") in actions


def test_another_idea_tells_the_other_chats_who_changed_it(tmp_path):
    cmd, _, told, _ = build(tmp_path)
    run(cmd, "")

    cmd.press(OWNER, "menu otra 2026-10-21 cena", who="Eze")

    assert len(told.messages) == 1
    chat_id, text = told.messages[0]
    assert chat_id == OWNER
    assert text.startswith("🍽 Eze cambió la cena")
    assert "Tarta de acelga" in text


def test_another_idea_without_a_name_is_someone(tmp_path):
    cmd, _, told, _ = build(tmp_path)
    run(cmd, "")

    run(cmd, "otra 2026-10-21 almuerzo")

    assert told.messages[0][1].startswith("🍽 Alguien cambió el almuerzo")


def test_another_idea_that_comes_back_broken_keeps_the_dish(tmp_path):
    model = WeekModel()
    cmd, _, told, _ = build(tmp_path, model=model)
    run(cmd, "")
    model.reply = json.dumps({"plato": "", "ingredientes": []})

    run(cmd, "otra 2026-10-21 cena")

    assert cmd.meal_store.get(date(2026, 10, 21), DINNER).dish == "Plato 2 cena"
    assert told.messages == []


@pytest.mark.parametrize("text", ["otra", "otra mañana cena", "otra 2026-10-21 merienda", "otra 2026-12-01 cena"])
def test_another_idea_needs_a_day_and_a_meal_of_the_menu(tmp_path, text):
    cmd, _, told, _ = build(tmp_path)
    run(cmd, "")

    reply = run(cmd, text)

    assert reply.text
    assert told.messages == []
    assert cmd.meal_store.get(date(2026, 10, 21), DINNER).dish == "Plato 2 cena"


def test_another_idea_for_a_meal_that_is_off(tmp_path):
    cmd, model, _, _ = build(tmp_path, menu_lunch_at=None)
    run(cmd, "")

    run(cmd, "otra 2026-10-21 almuerzo")

    assert len(model.prompts) == 1


# --- por dónde entra --------------------------------------------------------


def test_the_menu_is_dispatched_and_pressable(tmp_path):
    cmd, _, _, _ = build(tmp_path)

    assert cmd._dispatch()["menu"] == cmd.menu
    assert "Plato 0 almuerzo" in cmd.press(OWNER, "menu")


def test_a_stranger_gets_the_denial(tmp_path):
    cmd, model, _, _ = build(tmp_path)

    reply = cmd.menu(999, "")

    assert "999" in reply
    assert model.prompts == []

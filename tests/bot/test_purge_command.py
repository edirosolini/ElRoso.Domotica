"""/depurar: solo para los chats de alertas, con vista previa y confirmación por botón."""

import os
from datetime import datetime, timedelta

import pytest

from homeauto.bot.commands import HELP, Commands, with_actions
from homeauto.cleanup import PLAN_TTL, Cleaner
from homeauto.lists import ListStore
from homeauto.schedule.history import HistoryStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import DAILY, Store
from homeauto.tele import Tele, TeleLink, TeleStore
from tests.conftest import StubRegistry, make_config

OWNER = 42
OTHER = 77
STRANGER = 99
NOW = datetime(2026, 10, 21, 12, 0)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


class Timer:
    def schedule(self, key, when, action):
        pass

    def unschedule(self, key):
        pass


@pytest.fixture
def house(tmp_path):
    clock = Clock()
    store = Store(tmp_path / "jobs.db")
    reminders = Reminders(store=store, timer=Timer(), announce=lambda job: None, clock=clock)
    link = TeleLink(TeleStore(tmp_path / "jobs.db"), clock=clock)
    config = make_config(
        allowed=(OWNER, OTHER), alert_chat_ids=frozenset({OWNER}),
        screen_devices=("comedor",),
    )
    cleaner = Cleaner(config=config, reminders=reminders, tele=link, clock=clock)
    cmd = Commands(
        config=config, speakers=StubRegistry(), reminders=reminders, cleaner=cleaner, clock=clock
    )
    return {"cmd": cmd, "store": store, "reminders": reminders, "link": link, "clock": clock}


def stranger_job(house):
    return house["reminders"].add(STRANGER, NOW + timedelta(hours=1), "regar", repeat=DAILY)


def old_tele(house, alias="vieja"):
    house["link"].store.save(
        Tele(alias, "0.1", 1, ("play",), NOW - timedelta(days=8), "192.168.68.30")
    )


def detail(house, what="avisos", chat_id=OWNER):
    return with_actions(house["cmd"].purge, chat_id, what)


def test_a_chat_off_the_list_gets_its_id(house):
    reply = detail(house, "", chat_id=STRANGER)

    assert str(STRANGER) in reply.text
    assert reply.actions == ()


def test_a_chat_that_is_not_an_alert_chat_is_refused(house):
    stranger_job(house)

    reply = detail(house, "", chat_id=OTHER)

    assert reply.text == "Solo los chats de alertas pueden depurar."
    assert reply.actions == ()


def test_without_a_cleaner_it_says_so(tmp_path):
    cmd = Commands(
        config=make_config(allowed=(OWNER,)), speakers=StubRegistry(),
    )

    assert cmd.purge(OWNER, "") == "No tengo con qué depurar."


def test_the_overview_counts_and_offers_to_see_each_category(house):
    stranger_job(house)
    old_tele(house)

    reply = detail(house, "")

    assert "Teles: 1" in reply.text
    assert "Avisos: 1" in reply.text
    assert reply.actions == (("Ver teles (1)", "depurar teles"), ("Ver avisos (1)", "depurar avisos"))


def test_an_empty_overview_offers_nothing(house):
    reply = detail(house, "")

    assert reply.text == "🧹 No hay nada para depurar."
    assert reply.actions == ()


def test_the_detail_offers_to_delete_or_cancel(house):
    stranger_job(house)

    reply = detail(house, "avisos")

    (delete, delete_data), (cancel, cancel_data) = reply.actions
    assert delete == "Borrar 1"
    assert delete_data.startswith("depurar ok ")
    assert cancel == "Cancelar"
    assert cancel_data.startswith("depurar no ")


def test_the_teles_detail_is_reached_by_its_name(house):
    old_tele(house)

    reply = detail(house, "teles")

    assert "vieja" in reply.text
    assert reply.actions[0] == ("Borrar 1", reply.actions[0][1])


def test_an_unknown_category_explains_the_command(house):
    reply = detail(house, "macetas")

    assert "/depurar teles" in reply.text
    assert "/depurar avisos" in reply.text


def test_every_purge_button_fits_in_the_callback_data(house):
    stranger_job(house)
    old_tele(house)

    actions = detail(house, "").actions + detail(house, "teles").actions + detail(house).actions

    for _label, data in actions:
        assert len(data.encode("utf-8")) <= 64, data


def test_the_delete_button_deletes(house):
    job = stranger_job(house)
    [(_, data), _cancel] = detail(house).actions

    answer = house["cmd"].press(OWNER, data, who="Cin")

    assert answer == "🧹 Borré 1 de 1."
    assert house["store"].get(job.id) is None


def test_the_cancel_button_deletes_nothing(house):
    job = stranger_job(house)
    [(_, ok), (_, no)] = detail(house).actions

    assert house["cmd"].press(OWNER, no) == "Listo, no borré nada."
    assert "Venció" in house["cmd"].press(OWNER, ok)
    assert house["store"].get(job.id) is not None


def test_an_expired_plan_asks_to_start_again(house):
    job = stranger_job(house)
    [(_, data), _cancel] = detail(house).actions
    house["clock"].now += PLAN_TTL + timedelta(seconds=1)

    assert house["cmd"].press(OWNER, data) == "Venció, pedilo de nuevo con /depurar."
    assert house["store"].get(job.id) is not None


def test_a_non_alert_chat_cannot_press_delete(house):
    job = stranger_job(house)
    [(_, data), _cancel] = detail(house).actions

    assert house["cmd"].press(OTHER, data) == "Solo los chats de alertas pueden depurar."
    assert house["store"].get(job.id) is not None


def test_delete_is_only_a_button(house):
    """Escrito o por el router, «depurar ok …» no borra: es solo de botón."""
    job = stranger_job(house)
    [(_, data), _cancel] = detail(house).actions

    typed = house["cmd"]._dispatch()["depurar"](OWNER, data.removeprefix("depurar "))

    assert "/depurar teles" in typed
    assert house["store"].get(job.id) is not None
    assert house["cmd"].press(OWNER, data) == "🧹 Borré 1 de 1."


def test_purge_is_dispatched_by_name(house):
    assert house["cmd"]._dispatch()["depurar"] == house["cmd"].purge


def test_the_help_offers_purge():
    line = next(line for line in HELP.splitlines() if "/depurar" in line)

    assert "/depurar teles" in line or "alertas" in line


# --- historial, audio y listas ---


@pytest.fixture
def full(tmp_path):
    """Una casa con historial, listas y cache de audio, cada una con algo para borrar."""
    clock = Clock()
    db = tmp_path / "jobs.db"
    store = Store(db)
    history = HistoryStore(db)
    lists = ListStore(db, clock=lambda: NOW - timedelta(days=40))
    cache = tmp_path / "cache"
    cache.mkdir()
    reminders = Reminders(
        store=store, timer=Timer(), announce=lambda job: None, history=history, clock=clock
    )
    config = make_config(allowed=(OWNER, OTHER), alert_chat_ids=frozenset({OWNER}))
    cleaner = Cleaner(
        config=config, reminders=reminders, history=history, lists=lists, cache_dir=cache,
        clock=clock,
    )
    for days in (200, 100, 40):
        at = NOW - timedelta(days=days)
        history.record(days, OWNER, "reminder", DAILY, "la pastilla", at)
        history.mark_done(days, at, "Cin")
    lists.add("compras", ["leche"])
    wav = cache / "viejo.wav"
    wav.write_bytes(b"\0" * 10)
    moment = (NOW - timedelta(days=60)).timestamp()
    os.utime(wav, (moment, moment))
    cmd = Commands(
        config=config, speakers=StubRegistry(), reminders=reminders, cleaner=cleaner, clock=clock
    )
    return {"cmd": cmd, "history": history, "lists": lists, "wav": wav}


def ask(full, text, chat_id=OWNER):
    return with_actions(full["cmd"].purge, chat_id, text)


def test_the_overview_offers_history_audio_and_lists(full):
    reply = ask(full, "")

    assert "Historial: 3" in reply.text
    assert "Audio: 1" in reply.text
    assert "Listas: 1" in reply.text
    assert reply.actions == (
        ("Ver historial (3)", "depurar historial"),
        ("Ver audio (1)", "depurar audio"),
        ("Ver listas (1)", "depurar listas"),
    )


def test_the_history_asks_how_many_months_to_keep(full):
    reply = ask(full, "historial")

    assert "meses" in reply.text
    assert reply.actions == (
        ("Dejar 1 mes", "depurar historial 1"),
        ("Dejar 3 meses", "depurar historial 3"),
        ("Dejar 6 meses", "depurar historial 6"),
        ("Dejar 12 meses", "depurar historial 12"),
    )


def test_the_months_chosen_lead_to_the_detail_with_delete(full):
    data = ask(full, "historial").actions[1][1]

    reply = with_actions(full["cmd"].press, OWNER, data)

    assert "3 meses" in reply.text
    (delete, delete_data), (cancel, _) = reply.actions
    assert delete == "Borrar 2"
    assert cancel == "Cancelar"
    assert full["cmd"].press(OWNER, delete_data) == "🧹 Borré 2 de 2."
    assert full["history"].count_before(NOW) == 1


def test_the_months_can_be_written(full):
    reply = ask(full, "historial 6 meses")

    assert reply.actions[0][0] == "Borrar 1"


@pytest.mark.parametrize("months", ["0", "13", "-3", "+20"])
def test_months_out_of_range_are_explained_and_offer_nothing(full, months):
    reply = ask(full, f"historial {months}")

    assert "entre 1 y 12 meses" in reply.text
    assert reply.actions == ()


def test_audio_and_lists_are_reached_by_their_names(full):
    audio = ask(full, "audio")
    lists = ask(full, "listas")

    assert "audios sin usar" in audio.text
    assert audio.actions[0][0] == "Borrar 1"
    assert "leche" in lists.text
    assert lists.actions[0][0] == "Borrar 1"
    assert full["cmd"].press(OWNER, audio.actions[0][1]) == "🧹 Borré 1 de 1."
    assert not full["wav"].exists()


def test_every_new_purge_button_fits_in_the_callback_data(full):
    actions = (
        ask(full, "").actions + ask(full, "historial").actions
        + ask(full, "historial 12").actions + ask(full, "audio").actions
        + ask(full, "listas").actions
    )

    for _label, data in actions:
        assert len(data.encode("utf-8")) <= 64, data


@pytest.mark.parametrize("what", ["historial", "historial 3", "audio", "listas"])
def test_a_non_alert_chat_cannot_see_the_new_categories(full, what):
    reply = ask(full, what, chat_id=OTHER)

    assert reply.text == "Solo los chats de alertas pueden depurar."
    assert reply.actions == ()


@pytest.mark.parametrize("name, other", [("compras", "pendientes"), ("pendientes", "compras")])
def test_one_list_by_its_name_shows_and_deletes_only_that_list(full, name, other):
    full["lists"].add("pendientes", ["plomero"])

    reply = ask(full, name)

    shown = "leche" if name == "compras" else "plomero"
    hidden = "plomero" if name == "compras" else "leche"
    assert shown in reply.text
    assert hidden not in reply.text
    assert reply.actions[0][0] == "Borrar 1"
    assert full["cmd"].press(OWNER, reply.actions[0][1]) == "🧹 Borré 1 de 1."
    assert len(full["lists"].items(name)) == 0
    assert len(full["lists"].items(other)) == 1


def test_lists_by_the_general_name_shows_every_list(full):
    full["lists"].add("pendientes", ["plomero"])

    reply = ask(full, "lista")

    assert "leche" in reply.text
    assert "plomero" in reply.text
    assert reply.actions[0][0] == "Borrar 2"


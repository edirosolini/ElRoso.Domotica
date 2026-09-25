"""Los botones que acompañan la respuesta de un comando."""

from datetime import datetime

import pytest

from homeauto.bot.commands import Commands, Reply, with_actions
from homeauto.lists import SHOPPING, TODO, ListStore
from homeauto.pending import Conversation, PendingStore
from homeauto.route import Decision
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import Store

from tests.conftest import FakeSpeaker, StubRegistry, make_config
from tests.bot.test_conversation import ScriptedRouter
from tests.bot.test_voice_note import FakeTranscriber

OWNER = 42
STRANGER = 99
NOW = datetime(2026, 9, 25, 10, 0)


class FakeTimer:
    def schedule(self, key, when, action):
        pass

    def unschedule(self, key):
        pass


@pytest.fixture
def cmd(tmp_path):
    path = tmp_path / "jobs.db"
    return Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        reminders=Reminders(
            store=Store(path),
            timer=FakeTimer(),
            announce=lambda job: None,
            fired=FiredStore(path),
            clock=lambda: NOW,
        ),
        lists=ListStore(path),
        conversation=Conversation(PendingStore(path), clock=lambda: NOW),
        clock=lambda: NOW,
    )


def data(reply: Reply) -> list[str]:
    return [command for _label, command in reply.actions]


# --- la base -----------------------------------------------------------------


def test_a_command_without_buttons_answers_plain_text(cmd):
    reply = with_actions(cmd.devices, OWNER)

    assert reply.actions == ()
    assert "parlante" in reply.text


def test_buttons_from_one_command_do_not_leak_into_the_next(cmd):
    with_actions(cmd.timer, OWNER, "10m sacá la pizza")

    assert with_actions(cmd.devices, OWNER).actions == ()


# --- #4 deshacer lo programado -----------------------------------------------


def test_a_timer_offers_to_cancel_it(cmd):
    reply = with_actions(cmd.timer, OWNER, "10m sacá la pizza")

    job = cmd.reminders.list(OWNER)[0]
    assert reply.actions == ((f"Cancelar #{job.id}", f"cancelar {job.id}"),)


def test_an_alarm_offers_to_cancel_it(cmd):
    reply = with_actions(cmd.alarm, OWNER, "diaria 7:30 arriba")

    job = cmd.reminders.list(OWNER)[0]
    assert data(reply) == [f"cancelar {job.id}"]


def test_what_could_not_be_scheduled_offers_nothing(cmd):
    reply = with_actions(cmd.timer, OWNER, "cuando pueda")

    assert reply.actions == ()


def test_a_postponed_alarm_offers_to_cancel_it(cmd):
    cmd.reminders.fired.remember(OWNER, "arriba", "parlante", NOW)

    reply = with_actions(cmd.postpone, OWNER, "")

    job = cmd.reminders.list(OWNER)[0]
    assert data(reply) == [f"cancelar {job.id}"]


# --- #6 cancelar desde la lista ----------------------------------------------


def test_the_schedule_offers_to_cancel_each_one(cmd):
    cmd.timer(OWNER, "10m uno")
    cmd.timer(OWNER, "20m dos")

    reply = with_actions(lambda chat_id: cmd.list(chat_id), OWNER)

    ids = [job.id for job in cmd.reminders.list(OWNER)]
    assert reply.actions == tuple((f"Cancelar #{i}", f"cancelar {i}") for i in ids)


def test_an_empty_schedule_offers_nothing(cmd):
    assert with_actions(lambda chat_id: cmd.list(chat_id), OWNER).actions == ()


def test_a_long_schedule_does_not_become_a_wall_of_buttons(cmd):
    for minutes in range(1, 30):
        cmd.timer(OWNER, f"{minutes}m algo")

    reply = with_actions(lambda chat_id: cmd.list(chat_id), OWNER)

    assert len(reply.actions) == 20


# --- #7 tachar de las listas -------------------------------------------------


def test_the_shopping_list_offers_to_tick_each_item_and_to_empty_it(cmd):
    cmd.add_item(OWNER, "leche, pan")

    reply = with_actions(cmd.shopping, OWNER)

    ids = [item_id for item_id, _ in cmd.lists.entries(SHOPPING)]
    assert reply.actions == (
        ("✓ leche", f"sacar id:{ids[0]}"),
        ("✓ pan", f"sacar id:{ids[1]}"),
        ("Vaciar", "sacar todo"),
    )


def test_the_todo_list_buttons_name_their_list(cmd):
    cmd.add_item(OWNER, "a pendientes llamar al plomero")

    reply = with_actions(cmd.todo, OWNER)

    assert all(command.endswith("de pendientes") for command in data(reply))


def test_an_empty_list_offers_nothing(cmd):
    assert with_actions(cmd.shopping, OWNER).actions == ()


def test_ticking_removes_that_item_even_after_the_list_moved(cmd):
    """Con posiciones, sacar el primero corría a los demás y el botón sacaba otro."""
    cmd.add_item(OWNER, "leche, pan, yerba")
    buttons = dict(with_actions(cmd.shopping, OWNER).actions)

    cmd.press(OWNER, buttons["✓ leche"])
    reply = cmd.press(OWNER, buttons["✓ yerba"])

    assert cmd.lists.items(SHOPPING) == ["pan"]
    assert "yerba" in reply


def test_ticking_twice_explains_it_was_already_gone(cmd):
    cmd.add_item(OWNER, "leche")
    buttons = dict(with_actions(cmd.shopping, OWNER).actions)
    cmd.press(OWNER, buttons["✓ leche"])

    reply = cmd.press(OWNER, buttons["✓ leche"])

    assert "ya no estaba" in reply


def test_an_item_of_one_list_cannot_be_ticked_from_the_other(cmd):
    cmd.add_item(OWNER, "leche")
    item_id = cmd.lists.entries(SHOPPING)[0][0]

    cmd.remove_item(OWNER, f"id:{item_id} de pendientes")

    assert cmd.lists.items(SHOPPING) == ["leche"]


def test_a_long_item_still_fits_in_the_button(cmd):
    cmd.add_item(OWNER, "a pendientes " + "revisar la instalación eléctrica del garage " * 3)

    for label, command in with_actions(cmd.todo, OWNER).actions:
        assert len(command.encode()) <= 64
        assert len(label) <= 40


# --- #5 contestar la pregunta con un toque -----------------------------------


def test_the_repetition_question_offers_its_answers(cmd):
    cmd.router = ScriptedRouter(Decision("alarma", "7:30 arriba"))

    reply = with_actions(cmd.free_text, OWNER, "despertame a las siete y media")

    assert "¿Una sola vez" in reply.text
    assert [label for label, _ in reply.actions] == [
        "Una sola vez", "Todos los días", "De lunes a viernes",
    ]


def test_a_question_without_choices_offers_nothing(cmd):
    cmd.router = ScriptedRouter(Decision("timer", ""))

    reply = with_actions(cmd.free_text, OWNER, "poneme un timer")

    assert reply.actions == ()


def test_tapping_an_answer_continues_the_conversation(cmd):
    router = ScriptedRouter(
        Decision("alarma", "7:30 arriba"),
        Decision(None),
        Decision("alarma", "diaria 7:30 arriba"),
    )
    cmd.router = router
    asked = with_actions(cmd.free_text, OWNER, "despertame a las siete y media")
    buttons = dict(asked.actions)

    reply = with_actions(cmd.press, OWNER, buttons["Todos los días"])

    assert router.seen[-1].endswith("todos los días")
    assert cmd.reminders.list(OWNER)[0].repeat == "daily"
    assert data(reply) == [f"cancelar {cmd.reminders.list(OWNER)[0].id}"]


def test_what_was_understood_also_offers_to_undo_it(cmd):
    cmd.router = ScriptedRouter(Decision("timer", "10m sacá la pizza"))

    reply = with_actions(cmd.free_text, OWNER, "avisame en diez minutos lo de la pizza")

    assert reply.text.startswith("Entendí:")
    assert data(reply) == [f"cancelar {cmd.reminders.list(OWNER)[0].id}"]


def test_a_voice_note_carries_its_buttons(cmd):
    cmd.router = ScriptedRouter(Decision("timer", "10m sacá la pizza"))
    cmd.transcribe = FakeTranscriber(heard="avisame en diez minutos lo de la pizza")

    reply = cmd.heard(OWNER, b"OggS")

    assert data(reply) == [f"cancelar {cmd.reminders.list(OWNER)[0].id}"]


def test_a_stranger_gets_no_buttons(cmd):
    reply = with_actions(cmd.shopping, STRANGER)

    assert reply.actions == ()

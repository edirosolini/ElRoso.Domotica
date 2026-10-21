"""`/recordar` repite en los días marcados; `/timer` es de una sola vez; «Hecho» cierra."""

from datetime import datetime, timedelta

import pytest

from homeauto.bot.commands import HELP, Commands, with_actions
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import ALARM, REMINDER, Store

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
OTHER = 99
NOW = datetime(2026, 9, 28, 7, 0)  # lunes


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def fire(self, key):
        self.armed[key][1]()


@pytest.fixture
def cmd(tmp_path):
    path = tmp_path / "jobs.db"
    told = []
    reminders = Reminders(
        store=Store(path),
        timer=FakeTimer(),
        announce=lambda job: None,
        fired=FiredStore(path),
        awaiting=AwaitingStore(path),
        notify=lambda chat_id, text: told.append((chat_id, text)),
        clock=lambda: NOW,
        chat_ids=[OWNER, OTHER],
    )
    commands = Commands(
        config=make_config(allowed={OWNER, OTHER}),
        speakers=StubRegistry(parlante=FakeSpeaker()),
        reminders=reminders,
        clock=lambda: NOW,
    )
    commands.told = told
    return commands


def test_a_daily_reminder(cmd):
    reply = cmd.remind(OWNER, "diaria 8:00 tomar la pastilla")

    [job] = cmd.reminders.list(OWNER)
    assert job.kind == REMINDER
    assert job.repeat == "daily"
    assert job.when == NOW.replace(hour=8)
    assert job.message == "tomar la pastilla"
    assert reply.startswith("Recordatorio todos los días #")


def test_a_reminder_on_some_days(cmd):
    reply = cmd.remind(OWNER, "lun-vie 7:30 salir al colegio")

    [job] = cmd.reminders.list(OWNER)
    assert job.kind == REMINDER
    assert job.repeat == "weekly"
    assert job.weekdays == [1, 2, 3, 4, 5]
    assert "Recordatorio lun, mar, mié, jue, vie" in reply


def test_lun_vie_rings_on_holidays(cmd):
    cmd.remind(OWNER, "lun-vie 7:30 salir al colegio")

    [job] = cmd.reminders.list(OWNER)
    assert job.skip_holidays is False


def test_working_days_do_not_ring_on_holidays(cmd):
    reply = cmd.remind(OWNER, "hábiles 7:00 salida al colegio")

    [job] = cmd.reminders.list(OWNER)
    assert (job.kind, job.repeat, job.weekdays) == (REMINDER, "weekly", [1, 2, 3, 4, 5])
    assert job.skip_holidays is True
    assert "Recordatorio días hábiles" in reply
    assert "días hábiles" in cmd.list(OWNER)


def test_working_days_without_accent_too(cmd):
    cmd.remind(OWNER, "habiles 7:00 salida al colegio")

    [job] = cmd.reminders.list(OWNER)
    assert job.skip_holidays is True



def test_a_monthly_reminder(cmd):
    reply = cmd.remind(OWNER, "mensual 10 9:00 pagar la luz")

    [job] = cmd.reminders.list(OWNER)
    assert job.kind == REMINDER
    assert job.repeat == "monthly"
    assert job.monthday == 10
    assert job.when == datetime(2026, 10, 10, 9, 0)
    assert reply.startswith("Recordatorio el 10 de cada mes #")


def test_a_monthly_reminder_on_the_thirty_first_warns_about_short_months(cmd):
    reply = cmd.remind(OWNER, "mensual 31 9:00 pagar el alquiler")

    [job] = cmd.reminders.list(OWNER)
    assert job.when == datetime(2026, 9, 30, 9, 0)
    assert job.monthday == 31
    assert reply.endswith("Los meses que no tienen 31, el último día.")

def test_a_reminder_without_days_is_not_scheduled(cmd):
    reply = cmd.remind(OWNER, "8:00 tomar la pastilla")

    assert cmd.reminders.list(OWNER) == []
    assert "días" in reply
    assert "/timer" in reply


def test_a_reminder_with_days_needs_a_clock(cmd):
    reply = cmd.remind(OWNER, "lun-vie 10m algo")

    assert cmd.reminders.list(OWNER) == []
    assert "hora" in reply


def test_a_reminder_offers_to_cancel_it(cmd):
    reply = with_actions(cmd.remind, OWNER, "diaria 8:00 la pastilla")

    [job] = cmd.reminders.list(OWNER)
    assert reply.actions == ((f"Cancelar #{job.id}", f"cancelar {job.id}"),)


def test_a_timer_is_a_one_shot_reminder(cmd):
    cmd.timer(OWNER, "mañana 10:00 llamar al médico")

    [job] = cmd.reminders.list(OWNER)
    assert job.kind == REMINDER
    assert job.repeat == "once"


def test_an_alarm_is_still_an_alarm(cmd):
    cmd.alarm(OWNER, "diaria 6:30 arriba")

    [job] = cmd.reminders.list(OWNER)
    assert job.kind == ALARM


def test_the_list_tells_them_apart(cmd):
    cmd.alarm(OWNER, "diaria 7:30 arriba")
    cmd.remind(OWNER, "diaria 8:00 la pastilla")

    lines = cmd.list(OWNER).splitlines()

    assert lines[0].startswith("⏰") and "arriba" in lines[0]
    assert lines[1].startswith("🔔") and "la pastilla" in lines[1]


def test_the_help_explains_the_three(cmd):
    assert "/recordar diaria" in HELP
    assert "/recordar lun-vie" in HELP
    assert "/alarma" in HELP
    assert "/timer" in HELP


@pytest.mark.parametrize("command", ["recordar", "alarma"])
def test_the_monthly_example_of_the_help_really_schedules(cmd, command):
    example = f"/{command} mensual 10 9:00 pagar la luz"
    assert example in HELP

    run = cmd.remind if command == "recordar" else cmd.alarm
    run(OWNER, example.split(" ", 1)[1])

    [job] = cmd.reminders.list(OWNER)
    assert (job.repeat, job.monthday, job.message) == ("monthly", 10, "pagar la luz")


# --- el botón «Hecho» ---------------------------------------------------------


def ring(cmd, message="tomar la pastilla"):
    cmd.remind(OWNER, f"diaria 8:00 {message}")
    [job] = [j for j in cmd.reminders.list(OWNER) if j.message == message]
    cmd.reminders.timer.fire(str(job.id))
    return job


def test_done_answers_who_pressed_and_tells_the_rest(cmd):
    job = ring(cmd)

    reply = cmd.press(OWNER, f"hecho {job.id}", who="Eze")

    assert reply == "✅ Hecho: «tomar la pastilla»"
    assert cmd.told == [(OTHER, "✅ Eze marcó hecho: «tomar la pastilla»")]


def test_done_twice_says_it_was_already_done(cmd):
    job = ring(cmd)
    cmd.press(OWNER, f"hecho {job.id}", who="Eze")

    reply = cmd.press(OTHER, f"hecho {job.id}", who="Ana")

    assert "ya" in reply.lower()
    assert len(cmd.told) == 1


def test_done_without_a_name_still_works(cmd):
    job = ring(cmd)

    cmd.press(OWNER, f"hecho {job.id}")

    assert cmd.told == [(OTHER, "✅ Alguien marcó hecho: «tomar la pastilla»")]


def test_done_is_a_button_and_not_something_to_route(cmd):
    """El router no puede pedirlo: solo llega desde el aviso."""
    assert "hecho" not in cmd._dispatch()


def test_a_stranger_cannot_press_done(cmd):
    job = ring(cmd)

    reply = cmd.press(7, f"hecho {job.id}", who="Nadie")

    assert "No estás en la lista" in reply
    assert cmd.told == []


# --- «Borrar», el botón de los avisos de la pantalla ------------------------


def test_delete_button_works_from_any_chat_and_tells_the_rest(cmd):
    job = cmd.reminders.add(OWNER, NOW + timedelta(hours=1), "arriba")

    reply = cmd.press(OTHER, f"borrar {job.id}", who="Ana")

    assert reply == f"🗑 Borrado #{job.id}: «arriba»"
    assert cmd.reminders.store.get(job.id) is None
    assert cmd.told == [(OWNER, f"🗑 Ana borró #{job.id}: «arriba»")]


def test_delete_button_twice_says_it_was_gone(cmd):
    job = cmd.reminders.add(OWNER, NOW + timedelta(hours=1), "arriba")
    cmd.press(OTHER, f"borrar {job.id}", who="Ana")

    reply = cmd.press(OWNER, f"borrar {job.id}", who="Eze")

    assert "ya no" in reply.lower()
    assert len(cmd.told) == 1


def test_delete_without_a_name_still_works(cmd):
    job = cmd.reminders.add(OWNER, NOW + timedelta(hours=1), "arriba")

    cmd.press(OWNER, f"borrar {job.id}")

    assert cmd.told == [(OTHER, f"🗑 Alguien borró #{job.id}: «arriba»")]


def test_delete_is_a_button_and_not_something_to_route(cmd):
    assert "borrar" not in cmd._dispatch()


def test_a_stranger_cannot_press_delete(cmd):
    job = cmd.reminders.add(OWNER, NOW + timedelta(hours=1), "arriba")

    reply = cmd.press(7, f"borrar {job.id}", who="Nadie")

    assert "No estás en la lista" in reply
    assert cmd.reminders.store.get(job.id) is not None


def test_typed_cancel_is_still_only_the_owners(cmd):
    job = cmd.reminders.add(OWNER, NOW + timedelta(hours=1), "arriba")

    assert "No encontré" in cmd.cancel(OTHER, str(job.id))
    assert cmd.reminders.store.get(job.id) is not None


def test_someone_without_a_chat_marks_done_and_every_chat_hears(cmd):
    job = ring(cmd)

    reply = cmd.press_without_chat(f"hecho {job.id}", who="Abuela (pantalla)")

    assert reply == "✅ Hecho: «tomar la pastilla»"
    assert sorted(cmd.told) == [
        (OWNER, "✅ Abuela (pantalla) marcó hecho: «tomar la pastilla»"),
        (OTHER, "✅ Abuela (pantalla) marcó hecho: «tomar la pastilla»"),
    ]

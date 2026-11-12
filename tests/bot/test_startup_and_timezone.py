"""Two traps found by reading the logs of a real deployment."""

import asyncio
import threading
from datetime import datetime

import pytest

from homeauto import main


class FakeJobQueue:
    def __init__(self):
        self.scheduled = []

    def run_once(self, callback, when, name):
        self.scheduled.append((callback, when, name))

    def get_jobs_by_name(self, name):
        return []


def test_scheduled_time_carries_its_timezone():
    """APScheduler reads a naive datetime as UTC.

    We work in local time, so a naive 23:14 got scheduled at 23:14 UTC — three
    hours in the past here — and the timer fired instantly instead of later.
    """
    queue = FakeJobQueue()
    naive = datetime(2026, 8, 29, 23, 14)

    main.JobQueueTimer(queue).schedule("1", naive, lambda: None)

    _, when, _ = queue.scheduled[0]
    assert when.tzinfo is not None, "sin tzinfo, APScheduler lo interpreta como UTC"
    assert when.replace(tzinfo=None) == naive, "la hora de pared no debe moverse"
    assert when.utcoffset() == naive.astimezone().utcoffset()


class SpyReminders:
    def __init__(self):
        self.threads = []

    def start(self):
        self.threads.append(threading.current_thread().name)


class SpyNotifier:
    def __init__(self):
        self.loop = None

    def bind(self, loop):
        self.loop = loop


class SpyBot:
    def __init__(self, failing=()):
        self.menu = None
        self.published = []
        self.failing = set(failing)

    async def set_my_commands(self, commands, scope=None):
        chat_id = getattr(scope, "chat_id", None)
        if chat_id in self.failing:
            raise RuntimeError("Chat not found")
        self.published.append((chat_id, [command.command for command in commands]))
        if scope is None:
            self.menu = commands


class SpyApp:
    def __init__(self, failing=()):
        self.bot = SpyBot(failing)


@pytest.mark.asyncio
async def test_startup_does_not_re_arm_on_the_event_loop():
    """Catching up a missed job announces it, and announcing blocks.

    Done on the loop it deadlocks: the notification needs the very loop that is
    sitting there waiting for it, and discovery finds nothing.
    """
    reminders, notifier, app = SpyReminders(), SpyNotifier(), SpyApp()

    await main.build_post_init(notifier, reminders)(app)

    assert reminders.threads, "no se rearmó nada"
    assert reminders.threads[0] != threading.current_thread().name


@pytest.mark.asyncio
async def test_startup_binds_the_loop_and_publishes_the_menu():
    reminders, notifier, app = SpyReminders(), SpyNotifier(), SpyApp()

    await main.build_post_init(notifier, reminders)(app)

    assert notifier.loop is asyncio.get_running_loop()
    assert app.bot.menu is not None
    assert [command.command for command in app.bot.menu] == [n for n, _ in main.COMMAND_MENU]


@pytest.mark.asyncio
async def test_an_alert_chat_gets_the_menu_with_the_settings():
    reminders, notifier, app = SpyReminders(), SpyNotifier(), SpyApp()

    await main.build_post_init(notifier, reminders, alert_chats=(42,))(app)

    general = [name for name, _ in main.COMMAND_MENU]
    assert app.bot.published == [(None, general), (42, general + ["ajustes"])]


@pytest.mark.asyncio
async def test_a_chat_that_fails_to_get_its_menu_does_not_stop_the_startup(caplog):
    reminders, notifier, app = SpyReminders(), SpyNotifier(), SpyApp(failing={13})

    await main.build_post_init(notifier, reminders, alert_chats=(13, 42))(app)

    assert [chat for chat, _ in app.bot.published] == [None, 42]
    assert reminders.threads, "el arranque siguió"
    assert "13" in caplog.text


class SpyVacation:
    def __init__(self, order):
        self.order = order
        self.threads = []

    def start(self):
        self.threads.append(threading.current_thread().name)
        self.order.append("vacation")


@pytest.mark.asyncio
async def test_startup_rearms_the_end_of_the_vacations_before_the_alarms_off_the_loop():
    order = []
    reminders, notifier, app = SpyReminders(), SpyNotifier(), SpyApp()
    reminders.start = lambda: order.append("reminders")
    vacation = SpyVacation(order)

    await main.build_post_init(notifier, reminders, vacation=vacation)(app)

    assert order == ["vacation", "reminders"]
    assert vacation.threads[0] != threading.current_thread().name

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
    def __init__(self):
        self.menu = None

    async def set_my_commands(self, commands):
        self.menu = commands


class SpyApp:
    def __init__(self):
        self.bot = SpyBot()


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
    assert len(app.bot.menu) == len(main.COMMAND_MENU)

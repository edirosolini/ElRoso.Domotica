"""Composition root: wires the pieces and runs the Telegram bot.

Deliberately thin. Everything with a decision in it lives in a tested module;
what is here is assembly and process lifecycle, verified by running it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from homeauto.bot.commands import Commands
from homeauto.config import Config
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import Store
from homeauto.voice.caster import Caster
from homeauto.voice.media_server import MediaServer
from homeauto.voice.speaker import Speaker
from homeauto.voice.tts import PiperRunner, VoiceSynth

CONFIG_PATH = os.environ.get("NESTBOT_CONFIG", "/etc/nestbot/nestbot.env")
PYTHON_BIN = os.environ.get("NESTBOT_PYTHON", "/opt/nestbot/venv/bin/python")
VOICE_PATH = os.environ.get("NESTBOT_VOICE", "/opt/nestbot/voices/es_AR-daniela-high.onnx")
CACHE_DIR = os.environ.get("NESTBOT_CACHE", "/var/lib/nestbot/cache")
MEDIA_PORT = int(os.environ.get("NESTBOT_MEDIA_PORT", "8765"))
STATE_DIR = Path(os.environ.get("STATE_DIRECTORY", "/var/lib/nestbot"))

log = logging.getLogger("homeauto")

# Telegram only accepts a-z, 0-9 and underscore in command names: no accents.
# Aliases in Spanish are fine as long as they stay unaccented.
START_COMMANDS = ("start", "help", "ayuda")
SAY_COMMANDS = ("decir",)
VOLUME_COMMANDS = ("volumen", "volume")
STOP_COMMANDS = ("parar", "stop")
WHERE_COMMANDS = ("donde",)
TIMER_COMMANDS = ("timer", "recordar")
ALARM_COMMANDS = ("alarma",)
LIST_COMMANDS = ("lista",)
CANCEL_COMMANDS = ("cancelar",)
ALL_COMMANDS = (
    START_COMMANDS + SAY_COMMANDS + VOLUME_COMMANDS + STOP_COMMANDS + WHERE_COMMANDS
    + TIMER_COMMANDS + ALARM_COMMANDS + LIST_COMMANDS + CANCEL_COMMANDS
)


def local_ip() -> str:
    """The address this host uses to reach the LAN, so the speaker can call back."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.168.68.1", 1))  # no packet is sent, just route lookup
        return probe.getsockname()[0]


class JobQueueTimer:
    """Adapts python-telegram-bot's job queue to what Reminders expects.

    The announcement blocks (it synthesizes and waits for the speaker), so it
    runs in a worker thread instead of stalling the bot's event loop.
    """

    def __init__(self, job_queue):
        self.job_queue = job_queue

    def schedule(self, key, when, action):
        self.unschedule(key)

        async def run(_context):
            await asyncio.to_thread(action)

        self.job_queue.run_once(run, when=when, name=key)

    def unschedule(self, key):
        for job in self.job_queue.get_jobs_by_name(key):
            job.schedule_removal()


def build_speaker(config: Config) -> Speaker:
    cache_dir = Path(CACHE_DIR)
    return Speaker(
        synth=VoiceSynth(cache_dir=cache_dir, runner=PiperRunner(PYTHON_BIN, VOICE_PATH)),
        caster=Caster(config.cast_uuid),
        media_server=MediaServer(cache_dir, advertised_ip=local_ip(), port=MEDIA_PORT),
    )


def _argument_text(update: Update) -> str:
    """Everything after the command, with the original spacing."""
    text = (update.message.text or "") if update.message else ""
    _, _, rest = text.partition(" ")
    return rest


def register(app: Application, commands: Commands) -> None:
    async def reply(update: Update, answer: str) -> None:
        await update.message.reply_text(answer)

    async def on_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await reply(update, commands.start(update.effective_chat.id))

    async def on_say(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await reply(update, commands.say(update.effective_chat.id, _argument_text(update)))

    async def on_volume(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await reply(update, commands.volume(update.effective_chat.id, _argument_text(update)))

    async def on_stop(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await reply(update, commands.stop(update.effective_chat.id))

    async def on_where(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await reply(update, commands.where(update.effective_chat.id))

    app.add_handler(CommandHandler(list(START_COMMANDS), on_start))
    app.add_handler(CommandHandler(list(SAY_COMMANDS), on_say))
    app.add_handler(CommandHandler(list(VOLUME_COMMANDS), on_volume))
    app.add_handler(CommandHandler(list(STOP_COMMANDS), on_stop))
    async def on_timer(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await reply(update, commands.timer(update.effective_chat.id, _argument_text(update)))

    async def on_alarm(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await reply(update, commands.alarm(update.effective_chat.id, _argument_text(update)))

    async def on_list(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await reply(update, commands.list(update.effective_chat.id))

    async def on_cancel(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await reply(update, commands.cancel(update.effective_chat.id, _argument_text(update)))

    app.add_handler(CommandHandler(list(WHERE_COMMANDS), on_where))
    app.add_handler(CommandHandler(list(TIMER_COMMANDS), on_timer))
    app.add_handler(CommandHandler(list(ALARM_COMMANDS), on_alarm))
    app.add_handler(CommandHandler(list(LIST_COMMANDS), on_list))
    app.add_handler(CommandHandler(list(CANCEL_COMMANDS), on_cancel))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # 🔴 httpx logs the full request URL at INFO, and the Telegram API carries the
    # bot token inside the path: at INFO the token ends up in the journal in clear
    # text, forever. Keep this at WARNING.
    for noisy in ("httpx", "httpcore", "telegram.ext.Updater"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    config = Config.from_file(CONFIG_PATH)
    speaker = build_speaker(config)
    log.info("configuración leída, arrancando polling")

    app = Application.builder().token(config.telegram_token).build()

    reminders = Reminders(
        store=Store(STATE_DIR / "jobs.db"),
        timer=JobQueueTimer(app.job_queue),
        announce=lambda job: speaker.say(job.message),
    )
    commands = Commands(config=config, speaker=speaker, reminders=reminders, clock=datetime.now)
    register(app, commands)

    async def on_ready(_app) -> None:
        # Re-arm what was pending; anything already due while we were down fires now.
        reminders.start()

    app.post_init = on_ready
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

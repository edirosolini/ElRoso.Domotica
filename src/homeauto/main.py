"""Composition root: wires the pieces and runs the Telegram bot.

Deliberately thin. Everything with a decision in it lives in a tested module;
what is here is assembly and process lifecycle, verified by running it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime, time as clock_time
from pathlib import Path

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from homeauto.agenda.ical import CalendarClient
from homeauto.agenda.seen import SeenStore
from homeauto.agenda.service import AgendaService
from homeauto.agenda.watcher import EventWatcher
from homeauto.ask import ASK_TIMEOUT, Asker
from homeauto.route import Router
from homeauto.api import ApiServer, ApiService
from homeauto.bot.commands import Commands
from homeauto.briefing import Briefing
from homeauto.config import Config
from homeauto.polish import GoogleModel, Polisher, as_is
from homeauto.quiet import Hush, HushStore
from homeauto.schedule.announcer import Announcer
from homeauto.schedule.preferences import Preferences
from homeauto.schedule.reminders import Reminders
from homeauto.schedule.store import Store
from homeauto.voice.caster import Caster
from homeauto.voice.media_server import MediaServer
from homeauto.voice.broadcast import HouseVoice
from homeauto.voice.registry import SpeakerRegistry
from homeauto.voice.speaker import Speaker
from homeauto.voice.tts import (
    DEFAULT_LENGTH_SCALE,
    DEFAULT_SENTENCE_SILENCE,
    PiperRunner,
    VoiceSynth,
)
from homeauto.watch.loading import ChecksError, load_checks
from homeauto.watch.marks import Marks
from homeauto.watch.monitor import Monitor
from homeauto.watch.seq import SeqClient
from homeauto.watch.seq_watcher import SeqWatcher
from homeauto.watch.status import StatusStore
from homeauto.weather import RainWatcher, WeatherClient

CONFIG_PATH = os.environ.get("DOMOTICA_CONFIG", "/etc/domotica/domotica.env")
PYTHON_BIN = os.environ.get("DOMOTICA_PYTHON", "/opt/domotica/venv/bin/python")
VOICE_PATH = os.environ.get("DOMOTICA_VOICE", "/opt/domotica/voices/es_AR-daniela-high.onnx")
CACHE_DIR = os.environ.get("DOMOTICA_CACHE", "/var/lib/domotica/cache")
MEDIA_PORT = int(os.environ.get("DOMOTICA_MEDIA_PORT", "8765"))


def _knob(name: str, default: float | None) -> float | None:
    """One pacing knob from the environment, or its default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("%s no es un número (%r), uso el valor de siempre", name, raw)
        return default


def pacing_from_env() -> dict:
    """How the house should speak. Moved from the container, not from code."""
    return {
        "length_scale": _knob("DOMOTICA_LENGTH_SCALE", DEFAULT_LENGTH_SCALE),
        "sentence_silence": _knob("DOMOTICA_SENTENCE_SILENCE", DEFAULT_SENTENCE_SILENCE),
        "noise_scale": _knob("DOMOTICA_NOISE_SCALE", None),
        "noise_w": _knob("DOMOTICA_NOISE_W", None),
    }


def build_synth(cache_dir: Path | str) -> VoiceSynth:
    """Synthesis with its pacing, and the pacing inside the cache key.

    🔴 The two have to come from the same place. Keyed without it, changing how
    the house speaks leaves every phrase already said playing at the old pacing,
    with nothing in the log to explain it.
    """
    runner = PiperRunner(PYTHON_BIN, VOICE_PATH, **pacing_from_env())
    return VoiceSynth(
        cache_dir=cache_dir,
        runner=runner,
        voice=VOICE_PATH,
        pacing=runner.pacing,
    )
STATE_DIR = Path(os.environ.get("STATE_DIRECTORY", "/var/lib/domotica"))

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
DEVICES_COMMANDS = ("equipos",)
USE_COMMANDS = ("usar",)
OFF_COMMANDS = ("apagar",)
WEATHER_COMMANDS = ("clima", "tiempo")
ASK_COMMANDS = ("preguntar", "pregunta")
AGENDA_COMMANDS = ("agenda",)
STATUS_COMMANDS = ("estado",)
SILENCE_COMMANDS = ("silencio", "siesta")
SPEAK_COMMANDS = ("hablar",)
ALL_COMMANDS = (
    START_COMMANDS + SAY_COMMANDS + VOLUME_COMMANDS + STOP_COMMANDS + WHERE_COMMANDS
    + TIMER_COMMANDS + ALARM_COMMANDS + LIST_COMMANDS + CANCEL_COMMANDS
    + DEVICES_COMMANDS + USE_COMMANDS + OFF_COMMANDS + WEATHER_COMMANDS
    + AGENDA_COMMANDS + STATUS_COMMANDS + SILENCE_COMMANDS + SPEAK_COMMANDS
    + ASK_COMMANDS
)

# What Telegram offers when you type "/". Without registering this the commands
# work but are invisible: you have to know them by heart. Only the primary name
# of each one goes here; the aliases would just clutter the menu.
COMMAND_MENU = (
    ("decir", "Decirlo en voz alta ahora"),
    ("timer", "Avisar dentro de un rato — /timer 10m sacá la pizza"),
    ("alarma", "Avisar a una hora — /alarma 7:30 arriba"),
    ("lista", "Ver lo que está programado"),
    ("cancelar", "Cancelar por número — /cancelar 3"),
    ("silencio", "No hablar por un rato — /silencio 2h"),
    ("hablar", "Cancelar el silencio y volver a hablar"),
    ("volumen", "Cambiar el volumen, de 0 a 100"),
    ("parar", "Cortar lo que esté sonando"),
    ("apagar", "Cerrar la app y dejar el equipo en reposo"),
    ("clima", "Decir el pronóstico en voz alta"),
    ("preguntar", "Averiguar algo y contestarlo en voz alta"),
    ("agenda", "Qué queda hoy — /agenda mañana para el día siguiente"),
    ("estado", "Cómo están los servicios que vigilo"),
    ("equipos", "Qué equipos tengo y cuál está activo"),
    ("usar", "Cambiar el equipo por defecto — /usar tv"),
    ("ayuda", "Cómo se usa"),
)


# Half an hour is enough for a warning that fires at most once a day, and it
# keeps the free forecast requests down to a couple dozen.
RAIN_INTERVAL = 1800


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

        # 🔴 APScheduler reads a naive datetime as UTC. We work in local time, so
        # a naive 23:14 got scheduled at 23:14 UTC — three hours in the past here —
        # and the timer fired instantly. astimezone() on a naive value reads it as
        # local and attaches the offset, leaving the wall clock time untouched.
        if when.tzinfo is None:
            when = when.astimezone()

        self.job_queue.run_once(run, when=when, name=key)

    def unschedule(self, key):
        for job in self.job_queue.get_jobs_by_name(key):
            job.schedule_removal()


class ChatNotifier:
    """Sends a Telegram message from a worker thread.

    Announcements run off the event loop, so the send has to be handed back to
    it instead of being awaited where there is no loop.
    """

    def __init__(self, bot):
        self.bot = bot
        self.loop = None

    def bind(self, loop) -> None:
        self.loop = loop

    def __call__(self, chat_id: int, text: str) -> None:
        if self.loop is None:
            raise RuntimeError("todavía no hay event loop al que mandarle el aviso")
        future = asyncio.run_coroutine_threadsafe(
            self.bot.send_message(chat_id=chat_id, text=text), self.loop
        )
        future.result(timeout=30)


def local_timezone():
    """The real zone, not a fixed offset: DST changes matter for a daily job."""
    from tzlocal import get_localzone

    return get_localzone()


def schedule_calendar_jobs(app, watcher) -> None:
    """The look-ahead that announces an event before it starts."""

    async def look_ahead(_context):
        await asyncio.to_thread(watcher.check)

    app.job_queue.run_repeating(look_ahead, interval=60, first=30, name="calendar-watch")


def schedule_briefing(app, config, briefing, announce) -> None:
    """The morning summary.

    🔴 The time carries its timezone. APScheduler reads a naive time as UTC,
    and a briefing meant for 08:00 would land at 05:00.

    It does not depend on the calendar: with no calendar configured the weather
    and the state of the services are still worth hearing.
    """
    if config.briefing_at is None:
        return

    moment = clock_time(config.briefing_at.hour, config.briefing_at.minute, tzinfo=local_timezone())

    async def say_briefing(_context):
        await asyncio.to_thread(lambda: announce(briefing.text()))

    app.job_queue.run_daily(say_briefing, time=moment, name="briefing")
    log.info("resumen diario a las %s", moment.strftime("%H:%M"))


def build_post_init(notifier, reminders, api=None):
    """What has to happen once the loop is running, before serving anyone.

    🔴 `reminders.start()` must run off the loop. Catching up a missed job
    announces it, and announcing blocks: discovery finds nothing on the loop,
    and the chat notification deadlocks waiting for the very loop that is
    sitting there waiting for it.
    """

    async def post_init(app) -> None:
        notifier.bind(asyncio.get_running_loop())
        # The API needs the notifier bound: outside working hours it answers
        # through Telegram instead of the speakers.
        if api is not None:
            api.start()
        await asyncio.to_thread(reminders.start)
        await app.bot.set_my_commands(
            [BotCommand(name, description) for name, description in COMMAND_MENU]
        )
        log.info("menú de comandos registrado en Telegram")

    return post_init


def _alert(house: HouseVoice, text: str, urgent: bool, detail: str = "") -> None:
    """Say it if allowed, and always leave it written in the chat.

    The detail is written, never spoken: an HTTP status or a quoted log line
    is what you need to read and the last thing you want read out loud.
    """
    written = f"{text}\n{detail}" if detail else text
    result = house.announce(text, urgent=urgent, written=written)
    if result["spoken"]:
        house.tell_everyone(f"{'🚨' if urgent else '⚠️'} {written}")


def _announce(house: HouseVoice, text: str) -> None:
    """Say it out loud when allowed, and always leave it written in the chat."""
    result = house.announce(text)
    if result["spoken"]:
        house.tell_everyone(f"🔔 {text}")


def build_polisher(config: Config):
    """The rewriter for generated wording, or None when there is no key.

    Only text this service writes goes through it. What a person typed into
    /decir or a timer is said exactly as they wrote it.
    """
    # The bound method, not the object: everything downstream calls it like the
    # `as_is` default, and a Polisher is not callable on its own.
    return Polisher(
        model=GoogleModel(api_key=config.llm_api_key, model=config.llm_model)
    ).polish


def build_asker(config: Config) -> Asker | None:
    """Who answers a question, or None when there is no key.

    🔴 The same client as the polisher, configured the other way round: this one
    grounds in Google Search and waits far longer for it. Rewording a sentence
    has nothing to look up and nobody waits for prose; a question does and they
    do.
    """
    if not config.polish_enabled:
        return None
    return Asker(
        model=GoogleModel(
            api_key=config.llm_api_key,
            model=config.ask_model,
            search=True,
            timeout=ASK_TIMEOUT,
        )
    )


def build_router(config: Config) -> Router | None:
    """Who reads a message with no slash, or None when there is no key.

    🔴 The cheap model, and no search. Interpreting is not finding out: every
    free-text message pays this call, so it has to be the fast one. Grounding
    here would put thirty seconds in front of "bajá el volumen".
    """
    if not config.polish_enabled:
        return None
    return Router(
        model=GoogleModel(api_key=config.llm_api_key, model=config.llm_model)
    )


def build_speakers(config: Config) -> SpeakerRegistry:
    """One Speaker per configured device, sharing synthesis and the media server.

    Only the Caster differs: synthesizing the same phrase twice or running two
    HTTP servers would be waste.
    """
    cache_dir = Path(CACHE_DIR)
    synth = build_synth(cache_dir)
    media_server = MediaServer(cache_dir, advertised_ip=local_ip(), port=MEDIA_PORT)

    def build(device_uuid) -> Speaker:
        return Speaker(synth=synth, caster=Caster(device_uuid), media_server=media_server)

    return SpeakerRegistry(config.devices, build=build)


def _argument_text(update: Update) -> str:
    """Everything after the command, with the original spacing."""
    text = (update.message.text or "") if update.message else ""
    _, _, rest = text.partition(" ")
    return rest


def register(app: Application, commands: Commands) -> None:
    """Wire every command, running the work off the event loop.

    🔴 The command work must not run on the loop. Discovery uses zeroconf, which
    does blocking I/O: called from inside a running asyncio loop it finds
    nothing and every command answers "no encontré el dispositivo". Piper would
    also freeze the bot for the length of the synthesis.
    """

    def handler(run_command):
        async def callback(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
            # 🔴 Only a fresh message. With allowed_updates=ALL_TYPES an edit
            # arrives too, and there `update.message` is None: replying blew up
            # with AttributeError, and before that the command had already run
            # with an empty argument, because the text came from the same place.
            # Ignoring edits is also the right behaviour on its own — fixing a
            # typo must not set a second alarm.
            if update.message is None or update.effective_chat is None:
                log.debug("ignoro un update que no es un mensaje nuevo")
                return

            chat_id = update.effective_chat.id
            text = _argument_text(update)
            answer = await asyncio.to_thread(run_command, chat_id, text)
            await update.message.reply_text(answer)

        return callback

    routes = (
        (START_COMMANDS, lambda chat_id, _text: commands.start(chat_id)),
        (SAY_COMMANDS, commands.say),
        (VOLUME_COMMANDS, commands.volume),
        (STOP_COMMANDS, commands.stop),
        (WHERE_COMMANDS, lambda chat_id, _text: commands.devices(chat_id)),
        (TIMER_COMMANDS, commands.timer),
        (ALARM_COMMANDS, commands.alarm),
        (LIST_COMMANDS, lambda chat_id, _text: commands.list(chat_id)),
        (CANCEL_COMMANDS, commands.cancel),
        (DEVICES_COMMANDS, lambda chat_id, _text: commands.devices(chat_id)),
        (USE_COMMANDS, commands.use),
        (OFF_COMMANDS, commands.turn_off),
        (WEATHER_COMMANDS, commands.weather),
        (ASK_COMMANDS, commands.ask),
        (AGENDA_COMMANDS, commands.agenda_command),
        (STATUS_COMMANDS, commands.status),
        (SILENCE_COMMANDS, commands.silence),
        (SPEAK_COMMANDS, commands.speak),
    )
    for names, run_command in routes:
        app.add_handler(CommandHandler(list(names), handler(run_command)))

    # Anything without a slash. Registered last, so a real command never
    # reaches the interpreter and never pays for a model call.
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handler(commands.free_text))
    )


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
    if config.polish_enabled:
        polish = build_polisher(config)
        log.info("pulido de la redacción con %s", config.llm_model)
    else:
        polish = as_is
        log.info("sin LLM_API_KEY: el texto generado va tal cual")
    speakers = build_speakers(config)
    log.info("equipos configurados: %s", ", ".join(speakers.aliases))

    app = Application.builder().token(config.telegram_token).build()

    notifier = ChatNotifier(app.bot)
    db_path = STATE_DIR / "jobs.db"
    # The quiet window everyone consults: the fixed hours plus whatever
    # /silencio asked for. Built before its users, like the rest of the file.
    hush = Hush(hours=config.quiet_hours, store=HushStore(db_path))
    reminders = Reminders(
        store=Store(db_path),
        timer=JobQueueTimer(app.job_queue),
        announce=Announcer(
            speakers=speakers,
            notify=notifier,
            fallback=config.default_device,
            quiet=hush,
            polish=polish,
        ),
    )
    calendar = None
    agenda = None
    if config.calendar_enabled:
        calendar = CalendarClient(config.calendars, timezone=local_timezone())
        agenda = AgendaService(
            calendar=calendar,
            clock=lambda: datetime.now(local_timezone()),
            polish=polish,
        )
        log.info("calendarios configurados: %s", ", ".join(config.calendars))
    else:
        log.info("sin calendarios configurados: /agenda queda apagado")

    house = HouseVoice(
        speakers=speakers,
        default_devices=[config.default_device],
        notify=notifier,
        chat_ids=config.allowed_chat_ids,
        quiet=hush,
    )

    monitor = None
    try:
        checks = load_checks(config.checks_file)
    except ChecksError as exc:
        # Bad config is worth failing loudly: a monitor nobody notices is off
        # is worse than no monitor.
        log.error("no pude leer %s: %s", config.checks_file, exc)
        raise
    if checks:
        monitor = Monitor(
            checks=checks,
            store=StatusStore(db_path),
            announce=lambda text, urgent, detail="": _alert(house, text, urgent, detail),
            polish=polish,
        )
        log.info("vigilando %s servicios: %s", len(checks), ", ".join(c.name for c in checks))
    else:
        log.info("sin servicios que vigilar en %s", config.checks_file)

    # One watcher per Seq: a VPS cannot report its own death, so each one is
    # read from here, and each keeps its own marks.
    seq_watchers = [
        SeqWatcher(
            client=SeqClient(base_url=instance.url, api_key=instance.api_key),
            marks=Marks(db_path),
            announce=lambda text, detail="": _alert(house, text, False, detail),
            polish=polish,
            cooldown_minutes=config.seq_cooldown,
            alias=instance.alias,
        )
        for instance in config.seq_instances
    ]
    for watcher in seq_watchers:
        log.info("vigilando los errores de %s", watcher.name)
    if not seq_watchers:
        log.info("Seq apagado: faltan SEQ_URL o SEQ_API_KEY")

    weather = WeatherClient(
        latitude=config.weather_lat,
        longitude=config.weather_lon,
        place=config.weather_place,
        polish=polish,
    )

    commands = Commands(
        config=config,
        speakers=speakers,
        agenda=agenda,
        monitor=monitor,
        reminders=reminders,
        preferences=Preferences(db_path),
        weather=weather,
        quiet=hush,
        asker=build_asker(config),
        router=build_router(config),
        clock=datetime.now,
    )
    register(app, commands)

    watcher = None
    if calendar is not None:
        watcher = EventWatcher(
            calendar=calendar,
            announce=lambda text: _announce(house, text),
            seen=SeenStore(db_path),
            lead_minutes=config.event_lead_minutes,
            clock=lambda: datetime.now(local_timezone()),
            polish=polish,
        )

    api = None
    if config.api_enabled:
        api = ApiServer(
            ApiService(
                token=config.api_token,
                speakers=speakers,
                default_devices=[config.default_device],
                notify=notifier,
                chat_ids=config.allowed_chat_ids,
                quiet=hush,
                polish=polish,
            ),
            port=config.api_port,
        )
    else:
        log.info("API deshabilitada: no hay API_TOKEN en la configuración")

    app.post_init = build_post_init(notifier, reminders, api)
    if watcher is not None:
        schedule_calendar_jobs(app, watcher)

    schedule_briefing(
        app,
        config,
        Briefing(agenda=agenda, weather=weather, monitor=monitor, polish=polish),
        lambda text: _announce(house, text),
    )

    rain = RainWatcher(
        weather=weather,
        announce=lambda text: _announce(house, text),
        marks=Marks(db_path),
        polish=polish,
    )

    async def check_rain(_context):
        await asyncio.to_thread(rain.check)

    app.job_queue.run_repeating(check_rain, interval=RAIN_INTERVAL, first=90, name="rain-watch")

    if monitor is not None:
        async def check_services(_context):
            await asyncio.to_thread(monitor.run_once)

        app.job_queue.run_repeating(
            check_services, interval=config.check_interval, first=20, name="service-watch"
        )

    for index, watcher in enumerate(seq_watchers):
        # 🔴 The watcher goes in as a default argument. Closing over the loop
        # variable would leave every job reading the last Seq of the list.
        async def check_seq(_context, seq_watcher=watcher):
            await asyncio.to_thread(seq_watcher.check)

        # Staggered so two instances do not query at the same second.
        app.job_queue.run_repeating(
            check_seq,
            interval=config.check_interval,
            first=40 + index * 10,
            name=f"seq-watch-{watcher.alias}" if watcher.alias else "seq-watch",
        )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

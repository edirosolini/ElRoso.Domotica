"""Composition root: arma las piezas y corre el bot de Telegram.

Delgado a propósito. Todo lo que tiene una decisión adentro vive en un módulo
con tests; acá solo hay cableado y ciclo de vida del proceso.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime, time as clock_time
from pathlib import Path

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from homeauto.agenda.ical import CalendarClient
from homeauto.agenda.seen import SeenStore
from homeauto.agenda.service import AgendaService
from homeauto.agenda.watcher import EventWatcher
from homeauto.ask import ASK_TIMEOUT, Asker
from homeauto.route import Router
from homeauto.api import ApiServer, ApiService
from homeauto.bot.commands import Commands
from homeauto.bible import VerseOfTheDay
from homeauto.briefing import Briefing
from homeauto.closing import Closing
from homeauto.economy import EconomyClient
from homeauto.news import NewsClient
from homeauto.config import Config
from homeauto.correct import as_written
from homeauto.correct import build as build_correction
from homeauto.listen import TIMEOUT as LISTEN_TIMEOUT, Transcriber
from homeauto.voice.voicemail import Voicemail
from homeauto.polish import GoogleModel, Polisher, as_is
from homeauto.translate import TRANSLATE_TIMEOUT, Translator
from homeauto.lists import ListStore
from homeauto.pending import Conversation, PendingStore
from homeauto.quiet import Hush, HushStore
from homeauto.schedule.announcer import Announcer
from homeauto.schedule.fired import FiredStore
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
from homeauto.weather import RainWatcher, WeatherClient, WeatherWatcher

CONFIG_PATH = os.environ.get("DOMOTICA_CONFIG", "/etc/domotica/domotica.env")
PYTHON_BIN = os.environ.get("DOMOTICA_PYTHON", "/opt/domotica/venv/bin/python")
VOICE_PATH = os.environ.get("DOMOTICA_VOICE", "/opt/domotica/voices/es_AR-daniela-high.onnx")
CACHE_DIR = os.environ.get("DOMOTICA_CACHE", "/var/lib/domotica/cache")
MEDIA_PORT = int(os.environ.get("DOMOTICA_MEDIA_PORT", "8765"))


def _knob(name: str, default: float | None) -> float | None:
    """Una perilla del ritmo, leída del entorno, o su default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("%s no es un número (%r), uso el valor de siempre", name, raw)
        return default


def pacing_from_env() -> dict:
    """Cómo tiene que hablar la casa. Se mueve desde el contenedor, no desde el código."""
    return {
        "length_scale": _knob("DOMOTICA_LENGTH_SCALE", DEFAULT_LENGTH_SCALE),
        "sentence_silence": _knob("DOMOTICA_SENTENCE_SILENCE", DEFAULT_SENTENCE_SILENCE),
        "noise_scale": _knob("DOMOTICA_NOISE_SCALE", None),
        "noise_w": _knob("DOMOTICA_NOISE_W", None),
    }


def build_synth(cache_dir: Path | str) -> VoiceSynth:
    """La síntesis con su ritmo, y el ritmo dentro de la clave del cache.

    Los dos salen del mismo lugar, o se reusa audio hecho con otro ritmo.
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

# Telegram solo acepta a-z, 0-9 y guion bajo en los nombres de comando: sin
# acentos. Los alias en español valen mientras no los lleven.
START_COMMANDS = ("start", "help", "ayuda")
SAY_COMMANDS = ("decir",)
CALL_COMMANDS = ("llamar", "llama")
VOLUME_COMMANDS = ("volumen", "volume")
STOP_COMMANDS = ("parar", "stop")
WHERE_COMMANDS = ("donde",)
TIMER_COMMANDS = ("timer", "recordar")
ALARM_COMMANDS = ("alarma",)
LIST_COMMANDS = ("lista",)
CANCEL_COMMANDS = ("cancelar",)
POSTPONE_COMMANDS = ("posponer",)
DEVICES_COMMANDS = ("equipos",)
USE_COMMANDS = ("usar",)
OFF_COMMANDS = ("apagar",)
WEATHER_COMMANDS = ("clima", "tiempo")
ASK_COMMANDS = ("preguntar", "pregunta")
CALC_COMMANDS = ("calcular", "convertir")
ADD_COMMANDS = ("agregar",)
SHOPPING_COMMANDS = ("compras",)
TODO_COMMANDS = ("pendientes",)
REMOVE_COMMANDS = ("sacar",)
TRANSLATE_COMMANDS = ("traducir",)
AGENDA_COMMANDS = ("agenda",)
STATUS_COMMANDS = ("estado",)
SILENCE_COMMANDS = ("silencio", "siesta")
SPEAK_COMMANDS = ("hablar",)
ALL_COMMANDS = (
    START_COMMANDS + SAY_COMMANDS + CALL_COMMANDS + VOLUME_COMMANDS + STOP_COMMANDS + WHERE_COMMANDS
    + TIMER_COMMANDS + ALARM_COMMANDS + LIST_COMMANDS + CANCEL_COMMANDS
    + DEVICES_COMMANDS + USE_COMMANDS + OFF_COMMANDS + WEATHER_COMMANDS
    + AGENDA_COMMANDS + STATUS_COMMANDS + SILENCE_COMMANDS + SPEAK_COMMANDS
    + ASK_COMMANDS + CALC_COMMANDS
    + ADD_COMMANDS + SHOPPING_COMMANDS + TODO_COMMANDS + REMOVE_COMMANDS
    + TRANSLATE_COMMANDS + POSTPONE_COMMANDS
)

# Lo que ofrece Telegram al escribir "/". Corto a propósito: el resto sigue
# andando escrito y está listado en `HELP`, el catálogo completo.
COMMAND_MENU = (
    ("decir", "Decirlo en voz alta ahora"),
    ("llamar", "Llamar a la casa — /llamar a cenar"),
    ("alarma", "Avisar a una hora — /alarma 7:30 arriba"),
    ("lista", "Ver y cancelar lo que está programado"),
    ("silencio", "No hablar por un rato — /silencio 2h"),
    ("preguntar", "Averiguar algo y contestarlo en voz alta"),
    ("compras", "Qué falta comprar — /agregar leche, pan"),
    ("equipos", "Qué equipos tengo y cuál está activo"),
    ("ayuda", "Todos los comandos y cómo se usan"),
)


# El botón abajo del aviso de una alarma o un timer.
SNOOZE_ACTIONS = (("Posponer 10 min", "posponer 10m"),)

# Un error que no llega al chat se ve igual que un bot colgado.
BROKEN = "🔴 No pude procesar la solicitud: {reason}"

# El «escribiendo…» de Telegram no se ve en todos los clientes. Esta burbuja
# se edita después con la respuesta.
WORKING = "⏳ Procesando…"

# Un comando dicho es una oración; más que esto es un monólogo.
MAX_VOICE_SECONDS = 60

# Media hora alcanza para un aviso que sale como mucho una vez por día, y deja
# los pedidos al pronóstico gratuito en un par de docenas.
RAIN_INTERVAL = 1800


def local_ip() -> str:
    """La dirección con la que este host sale a la LAN, para que el parlante vuelva."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.168.68.1", 1))  # no packet is sent, just route lookup
        return probe.getsockname()[0]


class JobQueueTimer:
    """Adapta la job queue de python-telegram-bot a lo que espera Reminders.

    El anuncio bloquea (sintetiza y espera al parlante), así que corre en un
    hilo aparte en vez de frenar el event loop del bot.
    """

    def __init__(self, job_queue):
        self.job_queue = job_queue

    def schedule(self, key, when, action):
        self.unschedule(key)

        async def run(_context):
            await asyncio.to_thread(action)

        # APScheduler lee un datetime naive como UTC y este proyecto trabaja en
        # hora local. astimezone() le pega el offset sin mover el reloj.
        if when.tzinfo is None:
            when = when.astimezone()

        self.job_queue.run_once(run, when=when, name=key)

    def unschedule(self, key):
        for job in self.job_queue.get_jobs_by_name(key):
            job.schedule_removal()


class ChatNotifier:
    """Manda un mensaje de Telegram desde un hilo aparte.

    Los anuncios corren fuera del event loop, así que el envío se le devuelve
    a él en vez de esperarlo donde no hay loop.
    """

    def __init__(self, bot):
        self.bot = bot
        self.loop = None

    def bind(self, loop) -> None:
        self.loop = loop

    def __call__(self, chat_id: int, text: str, actions: tuple[tuple[str, str], ...] = ()) -> None:
        if self.loop is None:
            raise RuntimeError("todavía no hay event loop al que mandarle el aviso")
        markup = None
        if actions:
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(label, callback_data=data) for label, data in actions]]
            )
        future = asyncio.run_coroutine_threadsafe(
            self.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup), self.loop
        )
        future.result(timeout=30)


def local_timezone():
    """La zona real, no un offset fijo: los cambios de horario importan en un job diario."""
    from tzlocal import get_localzone

    return get_localzone()


def schedule_calendar_jobs(app, watcher) -> None:
    """La antelación con la que se anuncia un evento antes de que empiece."""

    async def look_ahead(_context):
        await asyncio.to_thread(watcher.check)

    app.job_queue.run_repeating(look_ahead, interval=60, first=30, name="calendar-watch")


def _schedule_daily(app, at, speak, name: str, label: str) -> None:
    """Un trabajo diario a hora fija, fuera del event loop.

    La hora lleva su zona: APScheduler lee una naive como UTC.
    """
    moment = clock_time(at.hour, at.minute, tzinfo=local_timezone())

    async def job(_context):
        await asyncio.to_thread(speak)

    app.job_queue.run_daily(job, time=moment, name=name)
    log.info("%s a las %s", label, moment.strftime("%H:%M"))


def schedule_briefing(app, config, briefing, announce) -> None:
    """El resumen de la mañana, agendado haya o no calendarios configurados."""
    if config.briefing_at is None:
        return

    def speak() -> None:
        summary = briefing.speech()
        announce(summary.spoken, summary.written)

    _schedule_daily(app, config.briefing_at, speak, name="briefing", label="resumen diario")


def schedule_closing(app, config, closing, announce) -> None:
    """El cierre del día, que se calla cuando no juntó nada que decir."""
    if config.closing_at is None:
        return

    def speak() -> None:
        said = closing.text()
        if said:
            announce(said)

    _schedule_daily(app, config.closing_at, speak, name="closing", label="cierre del día")


def build_post_init(notifier, reminders, api=None):
    """Lo que tiene que pasar con el loop ya corriendo, antes de atender a nadie.

    `reminders.start()` corre fuera del loop: recuperar un job perdido lo
    anuncia, y anunciar bloquea.
    """

    async def post_init(app) -> None:
        notifier.bind(asyncio.get_running_loop())
        # La API necesita el notificador atado: en horario de descanso contesta
        # por Telegram en vez de por los parlantes.
        if api is not None:
            api.start()
        await asyncio.to_thread(reminders.start)
        await app.bot.set_my_commands(
            [BotCommand(name, description) for name, description in COMMAND_MENU]
        )
        log.info("menú de comandos registrado en Telegram")

    return post_init


def _alert(house: HouseVoice, text: str, urgent: bool, detail: str = "") -> None:
    """Lo dice si se puede, y siempre lo deja escrito en el chat.

    El detalle se escribe, nunca se dice: un estado HTTP o la cita de un log es
    lo que hay que leer y lo último que querés escuchar.
    """
    written = f"{text}\n{detail}" if detail else text
    result = house.announce(text, urgent=urgent, written=written)
    if result["spoken"]:
        house.tell_everyone(f"{'🚨' if urgent else '⚠️'} {written}")


def _announce(house: HouseVoice, text: str, written: str | None = None) -> None:
    """Lo dice en voz alta si se puede, y siempre lo deja escrito en el chat.

    `written` lleva más que lo hablado cuando la fuente tiene las dos mitades:
    el resumen de la mañana escribe los titulares tal como los publicaron los
    medios, con dígitos y todo.
    """
    result = house.announce(text, written=written)
    if result["spoken"]:
        house.tell_everyone(f"🔔 {written or text}")


def build_polisher(config: Config):
    """El pulidor de lo que generamos, o None si no hay clave.

    Por acá solo pasa texto que escribe este servicio. Lo que una persona tipeó
    en /decir va por `build_corrector`, que arregla la escritura y no toca las
    palabras.
    """
    # El método atado, no el objeto: aguas abajo se lo llama como al default
    # `as_is`, y un Polisher no es invocable por sí solo.
    return Polisher(
        model=GoogleModel(api_key=config.llm_api_key, model=config.llm_model)
    ).polish


def build_corrector(config: Config):
    """El corrector de lo que tipeó una persona, o la identidad si no hay clave.

    No es el pulidor: este no puede cambiar una palabra. Recibe el reloj porque
    una comida sigue a la hora.
    """
    if not config.polish_enabled:
        return as_written
    return build_correction(
        model=GoogleModel(api_key=config.llm_api_key, model=config.llm_model)
    )


def build_asker(config: Config) -> Asker | None:
    """Quién contesta una pregunta, o None si no hay clave.

    El mismo cliente que el del pulido, configurado al revés: con búsqueda en
    Google y con un timeout mucho más largo.
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


def build_translator(config: Config) -> Translator | None:
    """Quién traduce, o None si no hay clave.

    El modelo barato y sin búsqueda: traducir tampoco es averiguar.
    """
    if not config.polish_enabled:
        return None
    return Translator(
        model=GoogleModel(
            api_key=config.llm_api_key,
            model=config.llm_model,
            timeout=TRANSLATE_TIMEOUT,
        )
    )


def build_router(config: Config) -> Router | None:
    """Quién lee un mensaje sin barra, o None si no hay clave.

    El modelo barato y sin búsqueda: cada mensaje suelto paga esta llamada.
    """
    if not config.polish_enabled:
        return None
    return Router(
        model=GoogleModel(api_key=config.llm_api_key, model=config.llm_model)
    )


def build_transcriber(config: Config) -> Transcriber | None:
    """Quién convierte una nota de voz en palabras, o None si no hay clave.

    El modelo barato y sin búsqueda, como el router: transcribir tampoco es
    averiguar.
    """
    if not config.polish_enabled:
        return None
    return Transcriber(
        model=GoogleModel(
            api_key=config.llm_api_key,
            model=config.llm_model,
            timeout=LISTEN_TIMEOUT,
        )
    )


def build_voicemail(synth) -> Voicemail:
    """La misma síntesis que usa el parlante, codificada para el chat."""
    return Voicemail(synth)


def build_speakers(config: Config, synth=None) -> SpeakerRegistry:
    """Un Speaker por equipo configurado, compartiendo síntesis y servidor de audio.

    Lo único distinto es el Caster: sintetizar dos veces la misma frase o
    levantar dos servidores HTTP sería desperdicio.
    """
    cache_dir = Path(CACHE_DIR)
    synth = synth or build_synth(cache_dir)
    media_server = MediaServer(cache_dir, advertised_ip=local_ip(), port=MEDIA_PORT)

    def build(device_uuid) -> Speaker:
        return Speaker(synth=synth, caster=Caster(device_uuid), media_server=media_server)

    return SpeakerRegistry(config.devices, build=build)


def _argument_text(update: Update) -> str:
    """Todo lo que sigue al comando, con los espacios originales."""
    text = (update.message.text or "") if update.message else ""
    _, _, rest = text.partition(" ")
    return rest


async def _say_working(message):
    """La burbuja que avisa que arrancó, o None si no se pudo mandar."""
    try:
        return await message.reply_text(WORKING)
    except Exception:  # noqa: BLE001 - la señal no puede costar la respuesta
        log.warning("no pude avisar que estaba trabajando")
        return None


async def _answer(waiting, message, text: str) -> None:
    """Convierte la burbuja de «procesando» en la respuesta, o la manda aparte."""
    if waiting is None:
        await message.reply_text(text)
        return
    try:
        await waiting.edit_text(text)
    except Exception:  # noqa: BLE001 - editar puede fallar, contestar no
        log.warning("no pude editar el mensaje de espera")
        await message.reply_text(text)


async def _drop(waiting, message, fallback: str) -> None:
    """Saca la burbuja de «procesando» cuando ya se mandó la nota de voz."""
    if waiting is None:
        return
    try:
        await waiting.delete()
    except Exception:  # noqa: BLE001 - si no se puede borrar, que diga algo
        log.warning("no pude borrar el mensaje de espera")
        await _answer(waiting, message, fallback)


def register(app: Application, commands: Commands) -> None:
    """Cablea todos los comandos, corriendo el trabajo fuera del event loop.

    El descubrimiento (zeroconf) y la síntesis (Piper) bloquean: en el loop no
    encuentran nada y congelan el bot.
    """

    def handler(run_command):
        async def callback(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
            # Solo un mensaje nuevo: con allowed_updates=ALL_TYPES también entra
            # una edición, y ahí `update.message` viene en None.
            if update.message is None or update.effective_chat is None:
                log.debug("ignoro un update que no es un mensaje nuevo")
                return

            chat_id = update.effective_chat.id
            text = _argument_text(update)
            waiting = await _say_working(update.message)
            try:
                answer = await asyncio.to_thread(run_command, chat_id, text)
            except Exception as exc:  # noqa: BLE001 - se contesta, no se calla
                log.exception("el comando se rompió")
                answer = BROKEN.format(reason=exc)
            await _answer(waiting, update.message, answer)

        return callback

    routes = (
        (START_COMMANDS, lambda chat_id, _text: commands.start(chat_id)),
        (SAY_COMMANDS, commands.say),
        (CALL_COMMANDS, commands.call),
        (VOLUME_COMMANDS, commands.volume),
        (STOP_COMMANDS, commands.stop),
        (WHERE_COMMANDS, lambda chat_id, _text: commands.devices(chat_id)),
        (TIMER_COMMANDS, commands.timer),
        (ALARM_COMMANDS, commands.alarm),
        (LIST_COMMANDS, lambda chat_id, _text: commands.list(chat_id)),
        (CANCEL_COMMANDS, commands.cancel),
        (POSTPONE_COMMANDS, commands.postpone),
        (DEVICES_COMMANDS, lambda chat_id, _text: commands.devices(chat_id)),
        (USE_COMMANDS, commands.use),
        (OFF_COMMANDS, commands.turn_off),
        (WEATHER_COMMANDS, commands.weather),
        (ASK_COMMANDS, commands.ask),
        (CALC_COMMANDS, commands.calculate),
        (ADD_COMMANDS, commands.add_item),
        (SHOPPING_COMMANDS, commands.shopping),
        (TODO_COMMANDS, commands.todo),
        (REMOVE_COMMANDS, commands.remove_item),
        (TRANSLATE_COMMANDS, commands.translate),
        (AGENDA_COMMANDS, commands.agenda_command),
        (STATUS_COMMANDS, commands.status),
        (SILENCE_COMMANDS, commands.silence),
        (SPEAK_COMMANDS, commands.speak),
    )
    for names, run_command in routes:
        app.add_handler(CommandHandler(list(names), handler(run_command)))

    async def listen(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        """Una nota de voz: se baja y se ejecuta como un mensaje escrito."""
        if update.message is None or update.effective_chat is None:
            return
        voice = getattr(update.message, "voice", None)
        if voice is None:
            return

        if voice.duration and voice.duration > MAX_VOICE_SECONDS:
            await update.message.reply_text(
                f"Ese audio es muy largo. Mandame uno de hasta {MAX_VOICE_SECONDS} segundos."
            )
            return

        waiting = await _say_working(update.message)
        try:
            audio = bytes(await (await voice.get_file()).download_as_bytearray())
            reply = await asyncio.to_thread(
                commands.heard,
                update.effective_chat.id,
                audio,
                voice.mime_type or "audio/ogg",
            )
        except Exception as exc:  # noqa: BLE001 - se contesta, no se calla
            log.exception("el audio se rompió")
            await _answer(waiting, update.message, BROKEN.format(reason=exc))
            return

        if reply.audio is None:
            await _answer(waiting, update.message, reply.text)
            return

        # A un audio le alcanza el audio: el texto sería leerlo dos veces.
        with open(reply.audio, "rb") as recorded:
            await update.message.reply_voice(recorded)
        await _drop(waiting, update.message, reply.text)

    app.add_handler(MessageHandler(filters.VOICE, listen))

    async def tap(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        """Un botón tocado: se saca el botón y se contesta abajo del aviso."""
        query = getattr(update, "callback_query", None)
        if query is None or query.data is None or update.effective_chat is None:
            return

        await query.answer()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001 - el botón que queda no impide contestar
            log.warning("no pude sacar el botón del aviso")

        try:
            answer = await asyncio.to_thread(commands.press, update.effective_chat.id, query.data)
        except Exception as exc:  # noqa: BLE001 - se contesta, no se calla
            log.exception("el botón se rompió")
            answer = BROKEN.format(reason=exc)
        await query.message.reply_text(answer)

    app.add_handler(CallbackQueryHandler(tap))

    # Todo lo que viene sin barra. Se registra último, así un comando de verdad
    # nunca llega al intérprete ni paga la llamada al modelo.
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handler(commands.free_text))
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx loguea la URL completa en INFO y el token de Telegram va en el path,
    # así que terminaría en el journal en claro.
    for noisy in ("httpx", "httpcore", "telegram.ext.Updater"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    config = Config.from_file(CONFIG_PATH)
    if config.polish_enabled:
        polish = build_polisher(config)
        log.info("pulido de la redacción con %s", config.llm_model)
    else:
        polish = as_is
        log.info("sin LLM_API_KEY: el texto generado va tal cual")
    # Un solo VoiceSynth: el parlante y la nota de voz comparten cache.
    synth = build_synth(Path(CACHE_DIR))
    speakers = build_speakers(config, synth)
    log.info("equipos configurados: %s", ", ".join(speakers.aliases))

    app = Application.builder().token(config.telegram_token).build()

    notifier = ChatNotifier(app.bot)
    db_path = STATE_DIR / "jobs.db"
    # El silencio que todos consultan: las horas fijas más lo que haya pedido
    # /silencio. Se arma antes que sus usuarios, como el resto del archivo.
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
            actions=SNOOZE_ACTIONS,
        ),
        fired=FiredStore(db_path),
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
        # Una config rota falla fuerte: un monitor que nadie nota que está apagado
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

    # Un watcher por Seq: un VPS no puede avisar de su propia muerte, así que
    # cada uno se lee desde acá y cada uno lleva sus marcas.
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
        translator=build_translator(config),
        router=build_router(config),
        conversation=Conversation(PendingStore(db_path)),
        lists=ListStore(db_path),
        transcribe=build_transcriber(config),
        voicemail=build_voicemail(synth),
        correct=build_corrector(config),
        # Solo para /llamar, que es texto nuestro; lo que escribe una persona
        # va por `correct`.
        polish=polish,
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

    economy = EconomyClient(polish=polish) if config.economy_enabled else None
    news = (
        NewsClient(config.news_feeds, count=config.news_count)
        if config.news_enabled
        else None
    )
    verse = VerseOfTheDay() if config.verse_enabled else None
    if news is not None:
        log.info("titulares de: %s", ", ".join(config.news_feeds))

    schedule_briefing(
        app,
        config,
        Briefing(
            agenda=agenda,
            weather=weather,
            monitor=monitor,
            economy=economy,
            news=news,
            verse=verse,
            # Los mismos clientes que vigilan de día: de madrugada el aviso
            # solo va al chat, así que a la mañana se recuerda.
            seq=[watcher.client for watcher in seq_watchers],
            polish=polish,
        ),
        lambda text, written=None: _announce(house, text, written),
    )

    schedule_closing(
        app,
        config,
        Closing(
            agenda=agenda,
            weather=weather,
            monitor=monitor,
            lists=ListStore(db_path),
            polish=polish,
        ),
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

    # Los otros cuatro avisos del cielo. Su propio job y sus propias marcas: la
    # lluvia tiene historia en la base desplegada y se deja como está.
    sky = WeatherWatcher(
        weather=weather,
        announce=lambda text: _announce(house, text),
        marks=Marks(db_path),
        polish=polish,
    )

    async def check_sky(_context):
        await asyncio.to_thread(sky.check)

    app.job_queue.run_repeating(check_sky, interval=RAIN_INTERVAL, first=120, name="sky-watch")

    if monitor is not None:
        async def check_services(_context):
            await asyncio.to_thread(monitor.run_once)

        app.job_queue.run_repeating(
            check_services, interval=config.check_interval, first=20, name="service-watch"
        )

    for index, watcher in enumerate(seq_watchers):
        # Por argumento por defecto: cerrar sobre la variable del for dejaría
        # todos los jobs leyendo el último Seq de la lista.
        async def check_seq(_context, seq_watcher=watcher):
            await asyncio.to_thread(seq_watcher.check)

        # Escalonado para que dos instancias no consulten en el mismo segundo.
        app.job_queue.run_repeating(
            check_seq,
            interval=config.check_interval,
            first=40 + index * 10,
            name=f"seq-watch-{watcher.alias}" if watcher.alias else "seq-watch",
        )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

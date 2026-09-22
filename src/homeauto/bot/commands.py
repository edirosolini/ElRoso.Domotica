"""La lógica de los comandos, sin nada de Telegram.

Cada método recibe el chat y el texto del argumento, y devuelve la respuesta a
mandar. Los fallos de un equipo se vuelven oraciones, nunca trazas: del otro
lado hay alguien con un teléfono, no leyendo un log.
"""

from __future__ import annotations

import contextvars
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable

from homeauto.agenda.ical import CalendarError
from homeauto.ask import NOT_SPOKEN, AskError
from homeauto.calc import CalcError, evaluate
from homeauto.aloud import strip_aloud
from homeauto.config import Config
from homeauto.listen import ListenError
from homeauto.lists import LISTS, SHOPPING, TODO, ListError, resolve
from homeauto.voice.voicemail import VoicemailError
from homeauto import slots, summon
from homeauto.correct import as_written
from homeauto.polish import as_is
from homeauto.route import Decision, RouteError
from homeauto.translate import TranslateError
from homeauto.schedule.store import DAILY, ONCE, WEEKLY
from homeauto.quiet import Hush
from homeauto.timespec import (
    TimeSpecError,
    format_weekdays,
    next_weekday,
    parse_duration,
    parse_schedule,
    parse_weekdays,
)
from homeauto.voice.caster import CastError
from homeauto.voice.registry import UnknownDevice
from homeauto.voice.tts import TtsError
from homeauto.weather import WeatherError

log = logging.getLogger(__name__)

DEVICE_ERRORS = (CastError, TtsError, UnknownDevice)
TARGET_WORD = "en"
ALL_WORD = "todos"

# Una tanda de alias adelante: "comedor", "comedor,recamara", "comedor, recamara".
_TARGET_LIST = re.compile(r"^([a-z0-9_-]+(?:\s*,\s*[a-z0-9_-]+)*)(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
_CLOCK = re.compile(r"\d{1,2}[:.]\d{2}")
# Los ítems de una lista, como los separa una persona: "leche, pan y yerba".
_ITEMS = re.compile(r"\s*,\s*|\s+y\s+")
# «de pendientes» al final de un /sacar.
_LIST_SUFFIX = re.compile(r"\s+(?:de|en)\s+(.+)$", re.IGNORECASE)
ALL_ITEMS = "todo"


class TargetError(Exception):
    """Alguno de los equipos pedidos no existe."""


# El pedido en curso quiere el parlante. Va en contextvar y no en el objeto:
# dos mensajes se atienden a la vez.
_ALOUD = contextvars.ContextVar("aloud", default=False)

# La respuesta sin el «Entendí: /clima», que grabado era el eco del pedido.
_SPOKEN = contextvars.ContextVar("spoken", default="")


@dataclass(frozen=True)
class Reply:
    """Lo que vuelve al chat: siempre el texto, a veces también una nota de voz."""

    text: str
    audio: Path | None = None

HELP = """Hola. Manejo los equipos de casa.

/decir <texto> — lo dice ahora
/decir en comedor <texto> — lo dice en ese equipo
/decir en comedor,recamara <texto> — en varios
/decir en todos <texto> — en toda la casa
/llamar a cenar — llama a la casa; sin nada, a la comida que toque
/timer 10m sacá la pizza — avisa dentro de un rato
/alarma 7:30 arriba — avisa a esa hora
/alarma diaria 7:30 arriba — todos los días
/alarma lun-vie 5:30 arriba — solo esos días
/lista — lo que está programado
/cancelar <n> — cancela uno
/silencio 2h — no habla por un rato · /hablar lo cancela
/volumen <0-100> — cambia el volumen
/parar — corta lo que esté sonando
/apagar — cierra la app y deja el equipo en reposo
/clima — el pronóstico
/preguntar <pregunta> — la averigua y te la contesta
/calcular 15 por 4 — hace la cuenta · /calcular 20 grados en fahrenheit convierte
/agregar leche, pan — a la lista de compras
/agregar a pendientes llamar al plomero — a la otra lista
/compras — qué falta comprar · /pendientes — qué falta hacer
/traducir hola — al inglés · /traducir al francés hola — al que pidas
/sacar 2 — saca ese número de la lista · /sacar todo la vacía
/agenda — qué te queda hoy · /agenda mañana
/estado — cómo están los servicios que vigilo
/equipos — qué equipos tengo y cuál está activo
/usar <equipo> — cambia el equipo por defecto (acepta varios y «todos»)

La hora se escribe como quieras: 10m, 5min, 2h, 90s, 1h30m, 23:15, 5.30, mañana 8:00.
Una hora que ya pasó se entiende como la de mañana.
Los días de una alarma van adelante de la hora: lun-vie, mar,jue, finde, sab.
Cualquier comando acepta «en <equipo>» adelante para mandarlo a otro lado.
Te contesto acá salvo que lo pidas: agregá «por el parlante» o «en voz alta» al final
y sale por los equipos. /decir y /llamar suenan siempre, y las alarmas también.

También me hablás sin barra: «creá una alarma» y te pregunto lo que falte.
«olvidalo» deja lo que estábamos armando.
Y me mandás una nota de voz: la escucho, hago lo que pidas y te contesto con otro audio."""


def format_when(when: datetime, now: datetime) -> str:
    """Un momento dicho como lo diría una persona."""
    days = (when.date() - now.date()).days
    clock = when.strftime("%H:%M")
    if days == 0:
        return f"hoy {clock}"
    if days == 1:
        return f"mañana {clock}"
    return f"{when.strftime('%d/%m')} {clock}"


class Commands:
    def __init__(
        self,
        config: Config,
        speakers,
        reminders=None,
        preferences=None,
        weather=None,
        agenda=None,
        monitor=None,
        quiet=None,
        asker=None,
        router=None,
        conversation=None,
        lists=None,
        translator=None,
        transcribe=None,
        voicemail=None,
        correct=as_written,
        polish=as_is,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.config = config
        self.speakers = speakers
        self.reminders = reminders
        self.preferences = preferences
        self.weather_client = weather
        self.agenda = agenda
        self.monitor = monitor
        self.quiet = quiet
        self.asker = asker
        self.router = router
        self.conversation = conversation
        self.lists = lists
        self.translator = translator
        self.transcribe = transcribe
        self.voicemail = voicemail
        self.correct = correct
        self.polish = polish
        self.clock = clock

    # --- permisos y destino ------------------------------------------------

    def _denial(self, chat_id: int) -> str | None:
        """Devuelve la negativa a mandar, o None si el chat puede seguir."""
        if self.config.is_allowed(chat_id):
            return None
        log.warning("chat %s rechazado", chat_id)
        return "No estás en la lista. Pedile al dueño que agregue tu ID: " + str(chat_id)

    def _enrollment_hint(self, chat_id: int) -> str:
        # Con la lista blanca vacía cualquiera maneja los parlantes. Se avisa y
        # se entrega el id que hace falta para cerrarla.
        if not self.config.is_open_enrollment:
            return ""
        return (
            f"\n\n⚠️ El bot está abierto: cualquiera que lo encuentre puede usarlo."
            f"\nTu chat ID es {chat_id}. Ponelo en ALLOWED_CHAT_IDS y reiniciá el servicio."
        )

    def _wanted_aloud(self, text: str) -> tuple[bool, str]:
        """Si se pidió la respuesta en voz alta, y el texto sin esa coletilla."""
        aloud, rest = strip_aloud(text)
        return aloud or _ALOUD.get(), rest

    def _resting(self) -> str | None:
        """La respuesta a mandar en vez de hablar, o None si puede sonar."""
        if self.quiet is not None and self.quiet.is_quiet(self.clock()):
            return f"Horario de descanso ({self.quiet.label}): no lo dije en voz alta."
        return None

    def _default_aliases(self, chat_id: int) -> list[str]:
        stored = self.preferences.default_device(chat_id) if self.preferences else None
        chosen = [a for a in (stored or "").split(",") if a and self.speakers.has(a)]
        return chosen or [self.config.default_device]

    def _parse_aliases(self, spec: str) -> list[str] | None:
        """Los alias de «en <spec>», o None si no es un destino."""
        if spec.lower() == ALL_WORD:
            return list(self.speakers.aliases)

        parts = [part.strip().lower() for part in spec.split(",")]
        parts = [part for part in parts if part]
        if not parts:
            return None

        unknown = [part for part in parts if not self.speakers.has(part)]
        if not unknown:
            return list(dict.fromkeys(parts))  # dedup, keeping the order typed
        if len(parts) > 1:
            # Una lista con comas es inequívocamente un destino: se dice qué está
            # mal en vez de hablar la mitad como si fuera el mensaje.
            raise TargetError(
                f"No conozco: {', '.join(unknown)}. Tengo: {', '.join(self.speakers.aliases)}"
            )
        # Una sola palabra desconocida es el mensaje: "/decir en casa hace frío".
        return None

    def _split_target(
        self, chat_id: int, text: str, default: list[str] | None = None
    ) -> tuple[list[str], str]:
        """Saca un «en <equipos>» de adelante, si nombra equipos que existen.

        `default` manda cuando nadie nombró un ambiente: un llamado a cenar es
        para la casa, no para el último parlante que usó este chat.
        """
        text = text.strip()
        head, _, rest = text.partition(" ")
        if head.lower() == TARGET_WORD:
            match = _TARGET_LIST.match(rest.strip())
            if match:
                aliases = self._parse_aliases(match.group(1))
                if aliases:
                    return aliases, (match.group(2) or "").strip()
        return (default or self._default_aliases(chat_id)), text

    def _broadcast(self, aliases: list[str], action) -> dict[str, str | None]:
        """Corre la acción en todos los equipos a la vez.

        En paralelo a propósito: uno tras otro, la misma frase arranca con un par
        de segundos de diferencia en cada ambiente y la casa hace eco.
        """
        def run(alias: str) -> str | None:
            try:
                action(self.speakers.get(alias))
                return None
            except DEVICE_ERRORS as exc:
                log.warning("falló %s: %s", alias, exc)
                return str(exc)

        with ThreadPoolExecutor(max_workers=len(aliases)) as pool:
            return dict(zip(aliases, pool.map(run, aliases)))

    @staticmethod
    def _summary(results: dict[str, str | None], done: str, failed: str) -> str:
        ok = [alias for alias, problem in results.items() if problem is None]
        bad = [f"{alias}: {problem}" for alias, problem in results.items() if problem]
        if not ok:
            return f"{failed}\n" + "\n".join(bad)
        text = f"{done} en {', '.join(ok)}"
        if bad:
            text += "\n\nNo pude en:\n" + "\n".join(bad)
        return text

    # --- comandos ----------------------------------------------------------

    def start(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial
        return HELP + self._enrollment_hint(chat_id)

    def say(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            aliases, message = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        if not message:
            return "¿Qué querés que diga? Ej: /decir la cena está lista"

        resting = self._resting()
        if resting:
            return f"{resting}\n\nDecía: «{message}»"

        # Se corrige, no se reescribe: solo cambia la escritura. La respuesta
        # muestra lo que salió por el parlante, no lo que se tipeó.
        spoken = self.correct(message)
        results = self._broadcast(aliases, lambda speaker: speaker.say(spoken))
        summary = self._summary(results, "Ya le avisé", "No pude decirlo en ninguno:")
        if all(problem is None for problem in results.values()):
            summary += f": «{spoken}»"
        return summary + self._enrollment_hint(chat_id)

    def call(self, chat_id: int, text: str = "") -> str:
        """Llama a la casa a algo. La frase la genera la casa.

        La persona da una intención, no las palabras, así que la frase se genera
        acá y pasa por el pulidor.
        """
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            # Un llamado es para toda la casa salvo que alguien nombre un
            # ambiente: llamar a cenar a un solo parlante no es "a todos".
            aliases, what = self._split_target(
                chat_id, text, default=list(self.speakers.aliases)
            )
        except TargetError as exc:
            return str(exc)

        spoken = summon.phrase(what, self.clock())

        resting = self._resting()
        if resting:
            return f"{resting}\n\nDecía: «{spoken}»"

        spoken = self.polish(spoken)
        results = self._broadcast(aliases, lambda speaker: speaker.say(spoken))
        summary = self._summary(results, "Ya le avisé", "No pude decirlo en ninguno:")
        if all(problem is None for problem in results.values()):
            summary += f": «{spoken}»"
        return summary

    def volume(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            aliases, rest = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        try:
            percent = int(rest.strip())
        except ValueError:
            return "El volumen va como número de 0 a 100. Ej: /volumen 40"

        results = self._broadcast(aliases, lambda speaker: speaker.set_volume(percent))
        return self._summary(results, f"Volumen en {percent}", "No pude cambiar el volumen:")

    def stop(self, chat_id: int, text: str = "") -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            aliases, _ = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        results = self._broadcast(aliases, lambda speaker: speaker.stop())
        return self._summary(results, "Cortado", "No pude parar:")

    def weather(self, chat_id: int, text: str = "") -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        aloud, text = self._wanted_aloud(text)
        try:
            aliases, _ = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        # Una sola consulta para toda la casa: el pronóstico no cambia por ambiente.
        try:
            spoken = self.weather_client.spoken()
        except WeatherError as exc:
            return str(exc)

        if not aloud:
            return spoken

        resting = self._resting()
        if resting:
            return f"{spoken}\n\n{resting}"

        results = self._broadcast(aliases, lambda speaker: speaker.say(spoken))
        summary = self._summary(results, "Dicho", "No pude decirlo en ninguno:")
        return f"{spoken}\n\n{summary}"

    def ask(self, chat_id: int, text: str = "") -> str:
        """Contesta una pregunta en voz alta y deja la respuesta entera escrita.

        Lo dicho y lo escrito son textos distintos: una respuesta de búsqueda
        está hecha de años y cifras. `Asker` las separa y esto solo reenvía.
        """
        denial = self._denial(chat_id)
        if denial:
            return denial

        if self.asker is None:
            return (
                "No tengo modelo para contestar preguntas. "
                "Cargá LLM_API_KEY en el archivo de entorno."
            )

        aloud, text = self._wanted_aloud(text)
        try:
            aliases, question = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        if not question.strip():
            return "Preguntame algo: /preguntar cuántos goles hizo Messi"

        try:
            answer = self.asker.ask(question)
        except AskError as exc:
            return str(exc)

        _SPOKEN.set(answer.spoken)
        if not aloud:
            return answer.written

        resting = self._resting()
        if resting:
            return f"{answer.written}\n\n{resting}"

        results = self._broadcast(aliases, lambda speaker: speaker.say(answer.spoken))
        summary = self._summary(results, "Dicho", "No pude decirlo en ninguno:")
        return f"{answer.written}\n\n{summary}"

    def calculate(self, chat_id: int, text: str = "") -> str:
        """Resuelve una cuenta o una conversión sin pasar por ningún modelo."""
        denial = self._denial(chat_id)
        if denial:
            return denial

        aloud, text = self._wanted_aloud(text)
        try:
            aliases, expression = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        if not expression.strip():
            return "Pasame una cuenta: /calcular 15 por 4"

        try:
            result = evaluate(expression)
        except CalcError as exc:
            return str(exc)

        if not aloud:
            return result.written
        if not result.spoken:
            return f"{result.written}\n\nEse número no lo puedo decir; te lo dejé escrito."

        _SPOKEN.set(result.spoken)
        resting = self._resting()
        if resting:
            return f"{result.written}\n\n{resting}"

        results = self._broadcast(aliases, lambda speaker: speaker.say(result.spoken))
        summary = self._summary(results, "Dicho", "No pude decirlo en ninguno:")
        return f"{result.written}\n\n{summary}"

    def translate(self, chat_id: int, text: str = "") -> str:
        """Traduce un texto y lo deja escrito. No sale por el parlante."""
        denial = self._denial(chat_id)
        if denial:
            return denial

        if self.translator is None:
            return (
                "No tengo modelo para traducir. "
                "Cargá LLM_API_KEY en el archivo de entorno."
            )

        aloud, text = self._wanted_aloud(text)
        if not text.strip():
            return "Decime qué traduzco: /traducir hola"

        try:
            translated = self.translator.translate(text)
        except TranslateError as exc:
            return str(exc)

        if aloud:
            return f"{translated}\n\n⚠️ Esto no lo digo: mi voz habla solo español."
        return translated

    # --- listas ------------------------------------------------------------

    def _no_lists(self) -> str:
        return "No tengo las listas configuradas."

    def _split_list(self, text: str) -> tuple[str, str]:
        """La lista nombrada adelante y lo que queda, o la de compras y todo.

        Se prueba el nombre más largo primero: "a la lista de compras leche"
        nombra una lista, "a comprar pan" no.
        """
        words = text.split()
        if not words or words[0].lower() not in ("a", "en"):
            return SHOPPING, text

        for size in range(len(words) - 1, 0, -1):
            try:
                name = resolve(" ".join(words[1:size + 1]))
            except ListError:
                continue
            return name, " ".join(words[size + 1:])
        return SHOPPING, text

    def add_item(self, chat_id: int, text: str = "") -> str:
        """Suma cosas a una lista, la de compras salvo que se nombre otra."""
        denial = self._denial(chat_id)
        if denial:
            return denial
        if self.lists is None:
            return self._no_lists()

        list_name, rest = self._split_list(text.strip())
        wanted = [item for item in _ITEMS.split(rest) if item.strip()]
        if not wanted:
            return "Decime qué agrego: /agregar leche, pan"

        added = self.lists.add(list_name, wanted)
        repeated = [item for item in wanted if item not in added]

        lines = []
        if added:
            lines.append(f"Agregado a {list_name}: {', '.join(added)}")
        if repeated:
            lines.append(f"Ya estaba en {list_name}: {', '.join(repeated)}")
        return "\n".join(lines)

    def shopping(self, chat_id: int, _text: str = "") -> str:
        return self._show(chat_id, SHOPPING)

    def todo(self, chat_id: int, _text: str = "") -> str:
        return self._show(chat_id, TODO)

    def _show(self, chat_id: int, list_name: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial
        if self.lists is None:
            return self._no_lists()

        items = self.lists.items(list_name)
        if not items:
            return f"La lista de {list_name} está vacía."

        lines = [f"{list_name.capitalize()} ({len(items)})"]
        lines += [f"{position}. {item}" for position, item in enumerate(items, start=1)]
        lines.append("\nSacá uno con /sacar <número>")
        return "\n".join(lines)

    def remove_item(self, chat_id: int, text: str = "") -> str:
        """Saca un ítem por su número, o vacía la lista entera."""
        denial = self._denial(chat_id)
        if denial:
            return denial
        if self.lists is None:
            return self._no_lists()

        list_name, what = SHOPPING, text.strip()
        suffix = _LIST_SUFFIX.search(what)
        if suffix:
            try:
                list_name = resolve(suffix.group(1))
                what = what[: suffix.start()].strip()
            except ListError:
                pass

        if what.lower() == ALL_ITEMS:
            emptied = self.lists.clear(list_name)
            if not emptied:
                return f"La lista de {list_name} ya estaba vacía."
            return f"Vacié {list_name}: {emptied} cosas menos."

        try:
            position = int(what.lstrip("#"))
        except ValueError:
            return "Decime el número. Ej: /sacar 2 (lo ves con /compras)"

        removed = self.lists.remove(list_name, position)
        if removed is None:
            return f"En {list_name} no hay ningún {position}. Fijate con /{list_name}"
        return f"Saqué de {list_name}: {removed}"

    def _dispatch(self) -> dict:
        """Todos los comandos alcanzables sin barra, por nombre.

        Vive con los comandos y no en el cableado de Telegram: el router nombra
        un comando, y nombrar no es transporte.
        """
        return {
            "decir": self.say,
            "llamar": self.call,
            "timer": self.timer,
            "alarma": self.alarm,
            "lista": lambda chat_id, _text="": self.list(chat_id),
            "cancelar": self.cancel,
            "silencio": self.silence,
            "hablar": self.speak,
            "volumen": self.volume,
            "parar": self.stop,
            "apagar": self.turn_off,
            "clima": self.weather,
            "agenda": self.agenda_command,
            "estado": self.status,
            "equipos": lambda chat_id, _text="": self.devices(chat_id),
            "usar": self.use,
            "preguntar": self.ask,
            "calcular": self.calculate,
            "agregar": self.add_item,
            "compras": self.shopping,
            "pendientes": self.todo,
            "sacar": self.remove_item,
            "traducir": self.translate,
        }

    def heard(self, chat_id: int, audio: bytes, mime: str = "audio/ogg") -> Reply:
        """Una nota de voz: se transcribe, se ejecuta y se contesta con otra."""
        denial = self._denial(chat_id)
        if denial:
            return Reply(denial)

        if self.transcribe is None:
            return Reply("No escucho audios. Escribime o usá /ayuda.")

        try:
            said = self.transcribe(audio, mime)
        except ListenError as exc:
            return Reply(f"{exc}. Probá de nuevo o escribime.")

        token = _SPOKEN.set("")
        try:
            answer = self.free_text(chat_id, said)
            spoken = _SPOKEN.get() or answer
        finally:
            _SPOKEN.reset(token)

        text = f"🎤 «{said}»\n{answer}"
        # Piper lee «500 g» como «quinientos ge»: eso se lee, no se escucha. Y
        # grabar el puntero al chat sin mandar el chat sería una burla.
        unsayable = any(c.isdigit() for c in spoken) or spoken.strip() == NOT_SPOKEN
        if self.voicemail is None or unsayable:
            return Reply(text)

        try:
            return Reply(text, self.voicemail(spoken))
        except VoicemailError as exc:
            log.warning("no pude grabar la respuesta: %s", exc)
            return Reply(text)

    def free_text(self, chat_id: int, text: str) -> str:
        """Ejecuta lo que pedía un mensaje sin barra.

        Un mensaje completo se ejecuta de una y avisa qué entendió, sin
        preguntar antes; `/cancelar` es el deshacer. A uno al que le falta un
        dato obligatorio no se le contesta un error: se le pregunta.
        """
        denial = self._denial(chat_id)
        if denial:
            return denial

        if self.router is None:
            return "No entiendo mensajes sueltos. Los comandos están en /ayuda."

        # Antes de rutear: el router se comería la coletilla al armar el argumento.
        aloud, text = strip_aloud(text)
        if aloud:
            token = _ALOUD.set(True)
            try:
                return self._route_and_run(chat_id, text)
            finally:
                _ALOUD.reset(token)
        return self._route_and_run(chat_id, text)

    def _route_and_run(self, chat_id: int, text: str) -> str:

        pending = self.conversation.get(chat_id) if self.conversation else None
        if pending and self.conversation.dropped(text):
            self.conversation.forget(chat_id)
            return f"Listo, lo dejo. No quedó ningún /{pending.command} armado."

        try:
            decision = self.router.route(text)
        except RouteError as exc:
            # Un comando que no se pudo interpretar no es una pregunta.
            if not pending:
                return str(exc)
            # En medio de una conversación casi nunca es un comando: "a las
            # siete" tampoco lo es. Decide el hilo.
            decision = Decision(None)

        note = ""
        if pending:
            if self._interrupts(pending, decision):
                self.conversation.forget(chat_id)
                note = f"Dejo a medio armar el /{pending.command}.\n\n"
                pending = None
            else:
                decision = self._continue(pending, text)
                if decision is None:
                    return "No te entendí. Probá con /ayuda."

        # Con uno pendiente esto nunca es None: `_continue` solo devuelve el
        # comando que se está armando, y solo se guardan los ejecutables.
        run = None if decision.is_question else self._dispatch().get(decision.command)
        if run is None:
            return note + self.ask(chat_id, text)

        asked = pending.asked if pending else ()
        thread = f"{pending.thread}\n{text}" if pending else text
        question = self._still_missing(decision, asked)
        if question:
            self.conversation.remember(chat_id, decision.command, thread, asked + (question.name,))
            return note + question.question

        if self.conversation:
            self.conversation.forget(chat_id)
        understood = f"/{decision.command} {decision.argument}".strip()
        answer = run(chat_id, decision.argument)
        if not _SPOKEN.get():
            _SPOKEN.set(answer)
        return f"{note}Entendí: {understood}\n\n{answer}"

    def _interrupts(self, pending, decision) -> bool:
        """Si este mensaje es una orden nueva y no la respuesta que se pidió.

        Solo interrumpe un comando *completo* y distinto. Algo dicho a medias es
        casi siempre el dato que faltaba, no una segunda cosa.
        """
        if decision.is_question or decision.command == pending.command:
            return False
        if decision.command not in self._dispatch():
            return False
        return slots.missing(decision.command, decision.argument) is None

    def _continue(self, pending, text: str):
        """Se vuelve a leer el hilo entero, así la respuesta se junta con lo anterior.

        El hilo pasa por el mismo prompt que un mensaje suelto en vez de por un
        segundo prompt que fusione la respuesta con el argumento. Cuesta una
        llamada más por turno y deja un solo prompt del que fiarse.
        """
        try:
            decision = self.router.route(f"{pending.thread}\n{text}")
        except RouteError:
            return None
        if decision.is_question or decision.command != pending.command:
            # El hilo lo confundió. Se queda en lo que se estaba armando en vez
            # de mandar media conversación a buscar en internet.
            return Decision(pending.command, "")
        return decision

    def _still_missing(self, decision, asked: tuple[str, ...]):
        """El dato a preguntar, o None cuando ya se puede ejecutar.

        Un dato ya preguntado no se vuelve a pedir: si la respuesta no lo trajo,
        preguntar dos veces es un loop, y el parser del comando lo explica
        mejor que una segunda pregunta.
        """
        if not self.conversation:
            return None
        slot = slots.missing(decision.command, decision.argument)
        return slot if slot and slot.name not in asked else None

    def agenda_command(self, chat_id: int, text: str = "") -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        if self.agenda is None:
            return (
                "No tengo ningún calendario configurado. "
                "Cargá la dirección privada en formato iCal en CALENDAR_URL_<nombre>."
            )

        aloud, text = self._wanted_aloud(text)
        try:
            aliases, when = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        try:
            spoken = self.agenda.spoken(when)
        except CalendarError as exc:
            return f"No pude leer el calendario: {exc}"
        except ValueError as exc:
            return str(exc)

        if not aloud:
            return spoken

        resting = self._resting()
        if resting:
            return f"{spoken}\n\n{resting}"

        results = self._broadcast(aliases, lambda speaker: speaker.say(spoken))
        summary = self._summary(results, "Dicho", "No pude decirlo en ninguno:")
        return f"{spoken}\n\n{summary}"

    def status(self, chat_id: int, text: str = "") -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        if self.monitor is None:
            return "No tengo servicios configurados para vigilar. Se cargan en checks.json."

        picture = self.monitor.snapshot()
        if not picture:
            return "Todavía no hice ninguna ronda de chequeos."

        lines = []
        for name, state in sorted(picture.items(), key=lambda item: (item[1].up, item[0])):
            mark = "🟢" if state.up else "🔴"
            lines.append(f"{mark} {name} — {state.detail}")
        return "\n".join(lines)

    def turn_off(self, chat_id: int, text: str = "") -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            aliases, _ = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        results = self._broadcast(aliases, lambda speaker: speaker.turn_off())
        summary = self._summary(results, "Apagado", "No pude apagar:")
        if any(problem is None for problem in results.values()):
            summary += "\n\nEl televisor se apaga solo si lo tenés configurado para hacerlo al perder señal."
        return summary

    def devices(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        active = self._default_aliases(chat_id)
        lines = [
            f"{alias}{'  ◀ activo' if alias in active else ''}"
            for alias in self.speakers.aliases
        ]
        return (
            "Equipos:\n" + "\n".join(lines)
            + "\n\nCambialo con /usar <equipo>, o /usar todos."
            + "\nTambién podés mandar uno suelto: /decir en comedor,recamara hola"
        )

    # Se conserva para que /donde siga andando; es la misma pregunta.
    where = devices

    def use(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        spec = text.strip().lower()
        if not spec:
            return "Decime cuál. Ej: /usar comedor (los ves con /equipos)"

        try:
            aliases = self._parse_aliases(spec)
        except TargetError as exc:
            return str(exc)
        if not aliases:
            known = ", ".join(self.speakers.aliases)
            return f"No conozco '{spec}'. Tengo: {known}"

        if self.preferences:
            self.preferences.set_default_device(chat_id, ",".join(aliases))
        return f"Listo, ahora uso {', '.join(aliases)}"

    # --- silencio ----------------------------------------------------------

    def silence(self, chat_id: int, text: str = "") -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial
        if not isinstance(self.quiet, Hush):
            return "No tengo el silencio a pedido configurado."

        asked = text.strip()
        if not asked:
            return self._silence_status()

        try:
            duration = parse_duration(asked)
        except TimeSpecError as exc:
            return str(exc)

        ends = self.quiet.start(duration)
        return f"Listo, no hablo hasta las {ends.strftime('%H:%M')}. /hablar lo cancela."

    def speak(self, chat_id: int, text: str = "") -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial
        if not isinstance(self.quiet, Hush):
            return "No tengo el silencio a pedido configurado."

        if not self.quiet.stop():
            return "No estaba en silencio."
        return "Listo, vuelvo a hablar."

    def _silence_status(self) -> str:
        ends = self.quiet.until()
        if ends is not None:
            return f"En silencio hasta las {ends.strftime('%H:%M')}. /hablar lo cancela."
        return (
            f"Estoy hablando. El horario de descanso va de {self.quiet.hours.label}. "
            "Para callarme un rato: /silencio 2h"
        )

    # --- programados -------------------------------------------------------

    def _schedule(
        self,
        chat_id: int,
        text: str,
        repeat: str,
        label: str,
        days: tuple[int, ...] | None = None,
    ) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            aliases, rest = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        now = self.clock()
        try:
            when, message = parse_schedule(rest, now=now)
        except TimeSpecError as exc:
            return str(exc)

        if days:
            # La hora ya rodó a su próxima ocurrencia; ahora se elige el día.
            when = next_weekday(when, days)

        job = self.reminders.add(
            chat_id, when, message, repeat=repeat, device=",".join(aliases), days=days
        )
        return (
            f"{label} #{job.id} en {', '.join(aliases)} "
            f"para {format_when(when, now)}: «{message}»"
        )

    def timer(self, chat_id: int, text: str) -> str:
        return self._schedule(chat_id, text, ONCE, "Programado")

    def alarm(self, chat_id: int, text: str) -> str:
        try:
            aliases, rest = self._split_target(chat_id, text)
        except TargetError as exc:
            return str(exc)

        head, _, tail = rest.strip().partition(" ")
        prefix = f"{TARGET_WORD} {','.join(aliases)} "
        if head.lower() in slots.DAILY_WORDS:
            return self._schedule(chat_id, prefix + tail, DAILY, "Alarma todos los días")

        days = parse_weekdays(head)
        if days:
            # Los días eligen la ocurrencia, así que lo que sigue tiene que ser
            # una hora: "lun-vie 10m" significaría diez minutos desde ahora.
            if not _CLOCK.fullmatch(tail.strip().split(" ")[0]):
                return "Con días de la semana necesito una hora. Ej: /alarma lun-vie 5:30 arriba"
            return self._schedule(
                chat_id, prefix + tail, WEEKLY, f"Alarma {format_weekdays(days)}", days=days
            )

        return self._schedule(chat_id, prefix + rest, ONCE, "Alarma")

    def list(self, chat_id: int) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        jobs = self.reminders.list(chat_id)
        if not jobs:
            return "No hay nada programado"

        now = self.clock()
        lines = [
            f"#{job.id} · {format_when(job.when, now)} · {', '.join(job.devices) or self.config.default_device}"
            f"{self._repetition(job)} — {job.message}"
            for job in jobs
        ]
        lines.append("\nCancelá con /cancelar <número>")
        return "\n".join(lines)

    @staticmethod
    def _repetition(job) -> str:
        if job.is_daily:
            return " · todos los días"
        if job.is_weekly:
            return f" · {format_weekdays(job.weekdays)}"
        return ""

    def cancel(self, chat_id: int, text: str) -> str:
        denial = self._denial(chat_id)
        if denial:
            return denial

        try:
            job_id = int(text.strip().lstrip("#"))
        except ValueError:
            return "Decime el número. Ej: /cancelar 3 (lo ves con /lista)"

        if not self.reminders.cancel(chat_id, job_id):
            return f"No encontré el recordatorio #{job_id}"
        return f"Cancelado #{job_id}"

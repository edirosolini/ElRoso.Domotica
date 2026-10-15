"""Las horas en que la casa duerme, el silencio que alguien pide a mano y las vacaciones.

Dentro de la ventana no se dice nada en voz alta: el mensaje igual llega a
Telegram, pero los parlantes se quedan callados. `Hush` agrega una ventana
encima de las fijas y el modo vacaciones, y contesta lo mismo que `QuietHours`.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Callable, Iterable

log = logging.getLogger(__name__)

# La clave del timer que avisa el fin de las vacaciones.
AWAY_END_KEY = "away-end"
AWAY_OVER = "🧳 Terminó el modo vacaciones, vuelvo a hablar."


def _parse_clock(raw: str, field: str) -> time:
    raw = raw.strip()
    try:
        hour, _, minute = raw.partition(":")
        return time(int(hour), int(minute or 0))
    except ValueError as exc:
        raise ValueError(f"{field} no es una hora válida: '{raw}'") from exc


@dataclass(frozen=True)
class QuietHours:
    start: time
    end: time

    @classmethod
    def parse(cls, start: str, end: str) -> "QuietHours":
        return cls(start=_parse_clock(start, "inicio"), end=_parse_clock(end, "fin"))

    @property
    def enabled(self) -> bool:
        return self.start != self.end

    @property
    def label(self) -> str:
        return f"{self.start.strftime('%H:%M')}–{self.end.strftime('%H:%M')}"

    def reason(self, moment: datetime | None = None) -> str:
        """Por qué la casa no habla."""
        return f"Horario de descanso ({self.label})"

    def is_away(self, moment: datetime | None = None) -> bool:
        return False

    def away_until(self, moment: datetime | None = None) -> datetime | None:
        return None

    def is_quiet(self, moment: datetime) -> bool:
        if not self.enabled:
            return False

        now = moment.time()
        if self.start < self.end:
            return self.start <= now < self.end
        # La ventana cruza la medianoche: 23:00–07:00 es "tarde hoy o temprano mañana".
        return now >= self.start or now < self.end


SCHEMA = """
CREATE TABLE IF NOT EXISTS hush (
    id    INTEGER PRIMARY KEY CHECK (id = 1),
    until TEXT NOT NULL
);
"""


class HushStore:
    """Una fila: hasta cuándo dura el silencio que alguien pidió.

    Se guarda en vez de tenerlo en memoria porque un reinicio en medio de la
    siesta devolvería la casa hablando.
    """

    TABLE = "hush"

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def until(self) -> datetime | None:
        with self._connect() as conn:
            row = conn.execute(f"SELECT until FROM {self.TABLE} WHERE id = 1").fetchone()
        if not row:
            return None
        try:
            return datetime.fromisoformat(row["until"])
        except ValueError:
            return None

    def set(self, moment: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO {self.TABLE} (id, until) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET until = excluded.until",
                (moment.isoformat(),),
            )

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute(f"DELETE FROM {self.TABLE} WHERE id = 1")


AWAY_SCHEMA = """
CREATE TABLE IF NOT EXISTS away (
    id    INTEGER PRIMARY KEY CHECK (id = 1),
    until TEXT NOT NULL
);
"""


class AwayStore(HushStore):
    """Una fila: hasta cuándo dura el modo vacaciones."""

    TABLE = "away"

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(AWAY_SCHEMA)


def away_label(ends: datetime) -> str:
    """La vuelta como se escribe: «25/10», con la hora si no es medianoche."""
    label = ends.strftime("%d/%m")
    if (ends.hour, ends.minute) != (0, 0):
        label += f" a las {ends.strftime('%H:%M')}"
    return label


def reason_of(quiet, moment: datetime | None = None) -> str:
    """El motivo de no hablar de cualquier forma de silencio."""
    reason = getattr(quiet, "reason", None)
    if reason is not None:
        return reason(moment)
    return f"Horario de descanso ({quiet.label})"


def away_of(quiet, moment: datetime | None = None) -> bool:
    """Si la casa está de vacaciones, para cualquier forma de silencio."""
    is_away = getattr(quiet, "is_away", None)
    return bool(is_away(moment)) if is_away is not None else False


class Hush:
    """El horario de descanso, un silencio pedido a mano y el modo vacaciones.

    Tiene la misma forma que `QuietHours`: quien lo consulta pregunta
    `is_quiet()` y lee `reason()`, sin enterarse de las otras reglas.
    """

    def __init__(
        self, hours: QuietHours, store: HushStore, clock=datetime.now, away: AwayStore | None = None
    ):
        self.hours = hours
        self.store = store
        self.clock = clock
        self.away = away

    def until(self, moment: datetime | None = None) -> datetime | None:
        """Cuándo termina el silencio pedido a mano, o None si no hay ninguno."""
        moment = moment or self.clock()
        ends = self.store.until()
        if ends is None:
            return None
        if moment >= ends:
            # Vencido: se borra acá para que nadie aguas abajo chequee dos veces.
            self.store.clear()
            return None
        return ends

    def start(self, duration: timedelta) -> datetime:
        ends = self.clock() + duration
        self.store.set(ends)
        return ends

    def stop(self) -> bool:
        """True si había un silencio que cortar."""
        if self.until() is None:
            return False
        self.store.clear()
        return True

    def away_until(self, moment: datetime | None = None) -> datetime | None:
        """Hasta cuándo dura el modo vacaciones, o None si no está activo."""
        if self.away is None:
            return None
        moment = moment or self.clock()
        ends = self.away.until()
        if ends is None:
            return None
        if moment >= ends:
            self.away.clear()
            return None
        return ends

    def is_away(self, moment: datetime | None = None) -> bool:
        return self.away_until(moment) is not None

    def start_away(self, until: datetime) -> datetime:
        if self.away is None:
            raise RuntimeError("no hay dónde guardar el modo vacaciones")
        self.away.set(until)
        return until

    def stop_away(self) -> bool:
        """True si había vacaciones que cortar."""
        if not self.is_away():
            return False
        self.away.clear()
        return True

    def reason(self, moment: datetime | None = None) -> str:
        """Por qué la casa no habla: las vacaciones o el descanso."""
        ends = self.away_until(moment)
        if ends is not None:
            return f"De vacaciones hasta el {away_label(ends)}"
        return f"Horario de descanso ({self.label})"

    @property
    def enabled(self) -> bool:
        return self.hours.enabled or self.until() is not None or self.is_away()

    @property
    def label(self) -> str:
        ends = self.until()
        if ends is not None:
            return f"hasta las {ends.strftime('%H:%M')}, a pedido"
        return self.hours.label

    def is_quiet(self, moment: datetime) -> bool:
        return (
            self.is_away(moment)
            or self.until(moment) is not None
            or self.hours.is_quiet(moment)
        )


class Vacation:
    """Arranca y corta el modo vacaciones, y avisa cuando termina."""

    def __init__(
        self,
        hush: Hush,
        timer,
        notify: Callable[[int, str], None],
        chat_ids: Iterable[int],
        clock: Callable[[], datetime] = datetime.now,
        stop_ringing: Callable[[], object] | None = None,
    ):
        self.hush = hush
        # Corta las alarmas que estén sonando.
        self.stop_ringing = stop_ringing
        # Lo mismo que espera `Reminders`: `schedule(key, when, action)` y `unschedule(key)`.
        self.timer = timer
        self.notify = notify
        self.chat_ids = list(chat_ids)
        self.clock = clock

    def start(self) -> None:
        """Rearma el aviso de fin tras un reinicio, o lo da si venció estando caído."""
        ends = self.hush.away.until() if self.hush.away is not None else None
        if ends is None:
            return
        if ends <= self.clock():
            self._finish()
        else:
            self._arm(ends)

    def begin(self, until: datetime, chat_id: int, who: str) -> datetime:
        """Activa las vacaciones hasta `until` y avisa a los otros chats."""
        self.hush.start_away(until)
        self._arm(until)
        if self.stop_ringing is not None:
            try:
                self.stop_ringing()
            except Exception:
                log.exception("could not stop the ringing alarms")
        self._tell(f"🧳 {who} activó vacaciones hasta el {away_label(until)}", skip=chat_id)
        return until

    def end(self, chat_id: int, who: str) -> bool:
        """Corta las vacaciones y avisa a los otros chats; False si no había."""
        self.timer.unschedule(AWAY_END_KEY)
        if not self.hush.stop_away():
            return False
        self._tell(f"🧳 {who} cortó las vacaciones", skip=chat_id)
        return True

    def _arm(self, when: datetime) -> None:
        self.timer.schedule(AWAY_END_KEY, when, self._finish)

    def _finish(self) -> None:
        """Avisa a todos que terminaron, si no se extendieron."""
        if self.hush.is_away(self.clock()):
            return
        self._tell(AWAY_OVER)

    def _tell(self, text: str, skip: int | None = None) -> None:
        for chat_id in self.chat_ids:
            if chat_id == skip:
                continue
            try:
                self.notify(chat_id, text)
            except Exception:
                log.exception("could not tell chat %s about the vacations", chat_id)

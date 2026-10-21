"""Persistencia de timers, alarmas y recordatorios.

Lo agendado tiene que sobrevivir un reinicio del contenedor: una alarma que
desaparece porque el servicio se actualizó a medianoche es peor que no tenerla.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from homeauto.timespec import next_weekday

ONCE = "once"
DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"
REPEATS = (ONCE, DAILY, WEEKLY, MONTHLY)

ALARM = "alarm"
REMINDER = "reminder"
KINDS = (ALARM, REMINDER)

# Para quién es un aviso: nadie en particular, todos o una persona del padrón.
NOBODY = "none"
EVERYONE = "all"
PERSON = "person"
ASSIGNEES = (NOBODY, EVERYONE, PERSON)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id  INTEGER NOT NULL,
    fires_at TEXT    NOT NULL,
    message  TEXT    NOT NULL,
    repeat   TEXT    NOT NULL DEFAULT 'once',
    device   TEXT,
    days     TEXT,
    kind     TEXT    NOT NULL DEFAULT 'alarm',
    monthday INTEGER,
    skip_holidays INTEGER NOT NULL DEFAULT 0,
    stock_id INTEGER,
    rota     TEXT,
    rota_from TEXT,
    assignee TEXT    NOT NULL DEFAULT 'none',
    assignee_id INTEGER,
    author_id INTEGER
);
CREATE INDEX IF NOT EXISTS jobs_by_time ON jobs (fires_at);
"""


@dataclass(frozen=True)
class Job:
    id: int
    chat_id: int
    when: datetime
    message: str
    repeat: str = ONCE
    device: str | None = None
    days: str | None = None
    kind: str = ALARM
    monthday: int | None = None
    skip_holidays: bool = False
    stock_id: int | None = None
    # Los nombres que se turnan, separados por coma, y el lunes desde el que se cuenta.
    rota: str | None = None
    rota_from: date | None = None
    # Para quién es (`NOBODY`, `EVERYONE` o `PERSON`), qué persona y qué persona lo creó.
    assignee: str = NOBODY
    assignee_id: int | None = None
    author_id: int | None = None
    # Al sonar: los chats a los que llega (None es todos) y el nombre con que se lo llama.
    audience: tuple[int, ...] | None = None
    addressee: str | None = None

    @property
    def is_reminder(self) -> bool:
        return self.kind == REMINDER

    @property
    def is_daily(self) -> bool:
        return self.repeat == DAILY

    @property
    def is_weekly(self) -> bool:
        return self.repeat == WEEKLY

    @property
    def is_monthly(self) -> bool:
        return self.repeat == MONTHLY

    @property
    def weekdays(self) -> list[int]:
        """Días ISO de un job semanal; vacío para todo lo demás."""
        return [int(part) for part in (self.days or "").split(",") if part.strip()]

    @property
    def devices(self) -> list[str]:
        """La columna guarda una lista separada por comas; lo común es un solo equipo."""
        return [part.strip() for part in (self.device or "").split(",") if part.strip()]

    @property
    def turns(self) -> list[str]:
        """Los nombres que se turnan, en orden; vacío si no rota."""
        return [part.strip() for part in (self.rota or "").split(",") if part.strip()]


def on_monthday(year: int, month: int, monthday: int, like: datetime) -> datetime:
    """El día `monthday` de ese mes a la hora de `like`; el último si el mes no lo tiene."""
    last = calendar.monthrange(year, month)[1]
    return like.replace(year=year, month=month, day=min(monthday, last))


def next_month(when: datetime, monthday: int) -> datetime:
    """El día `monthday` del mes que sigue al de `when`, a la misma hora."""
    year, month = (when.year + 1, 1) if when.month == 12 else (when.year, when.month + 1)
    return on_monthday(year, month, monthday, when)


def next_run(job: Job, after: datetime) -> datetime | None:
    """La ocurrencia del job que sigue a la de `after`; None si no repite."""
    if job.repeat == DAILY:
        return after + timedelta(days=1)
    if job.repeat == WEEKLY:
        # Busca desde el día siguiente al de `after`.
        return next_weekday(after + timedelta(days=1), job.weekdays)
    if job.repeat == MONTHLY and job.monthday:
        return next_month(after, job.monthday)
    return None


def pack_chats(chats: Iterable[int] | None) -> str | None:
    """Los chats como se guardan, separados por coma; None es todos."""
    return None if chats is None else ",".join(str(chat) for chat in chats)


def unpack_chats(text: str | None) -> tuple[int, ...] | None:
    """Los chats guardados con `pack_chats`; None es todos."""
    if text is None:
        return None
    return tuple(int(part) for part in text.split(",") if part.strip())


def check_assignee(assignee: str, assignee_id: int | None) -> None:
    """Rechaza una asignación que no existe o una persona sin id, o un id sin persona."""
    if assignee not in ASSIGNEES:
        raise ValueError(f"assignee inválido: {assignee}")
    if (assignee == PERSON) != (assignee_id is not None):
        raise ValueError("solo una asignación a una persona lleva su id")


def _validate(
    repeat: str,
    kind: str,
    days: Iterable[int] | None,
    monthday: int | None,
    skip_holidays: bool = False,
) -> str | None:
    """Chequea repetición, tipo, días, día del mes y feriados; devuelve los días como se guardan."""
    if repeat not in REPEATS:
        raise ValueError(f"repeat inválido: {repeat}")
    if kind not in KINDS:
        raise ValueError(f"kind inválido: {kind}")
    stored_days = ",".join(str(day) for day in sorted(days)) if days else None
    # Un job semanal sin días no encontraría nunca un día para disparar.
    if repeat == WEEKLY and not stored_days:
        raise ValueError("una alarma semanal necesita días")
    if repeat == MONTHLY and monthday not in range(1, 32):
        raise ValueError("una alarma mensual necesita el día del mes")
    if skip_holidays and repeat != WEEKLY:
        raise ValueError("solo lo semanal saltea feriados")
    return stored_days


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        chat_id=row["chat_id"],
        when=datetime.fromisoformat(row["fires_at"]),
        message=row["message"],
        repeat=row["repeat"],
        device=row["device"],
        days=row["days"],
        kind=row["kind"],
        monthday=row["monthday"],
        skip_holidays=bool(row["skip_holidays"]),
        stock_id=row["stock_id"],
        rota=row["rota"],
        rota_from=date.fromisoformat(row["rota_from"]) if row["rota_from"] else None,
        assignee=row["assignee"],
        assignee_id=row["assignee_id"],
        author_id=row["author_id"],
    )


class Store:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._add_missing_columns(conn)

    @staticmethod
    def _add_missing_columns(conn: sqlite3.Connection) -> None:
        """Hay bases creadas antes de que existiera la columna."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        if "device" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN device TEXT")
        if "days" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN days TEXT")
        if "kind" not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT '{ALARM}'")
        if "monthday" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN monthday INTEGER")
        if "skip_holidays" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN skip_holidays INTEGER NOT NULL DEFAULT 0")
        if "stock_id" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN stock_id INTEGER")
        if "rota" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN rota TEXT")
        if "rota_from" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN rota_from TEXT")
        if "assignee" not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN assignee TEXT NOT NULL DEFAULT '{NOBODY}'")
        if "assignee_id" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN assignee_id INTEGER")
        if "author_id" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN author_id INTEGER")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def add(
        self,
        chat_id: int,
        when: datetime,
        message: str,
        repeat: str = ONCE,
        device: str | None = None,
        days: Iterable[int] | None = None,
        kind: str = ALARM,
        monthday: int | None = None,
        skip_holidays: bool = False,
        stock_id: int | None = None,
        assignee: str = NOBODY,
        assignee_id: int | None = None,
        author_id: int | None = None,
    ) -> Job:
        stored_days = _validate(repeat, kind, days, monthday, skip_holidays)
        check_assignee(assignee, assignee_id)
        monthday = monthday if repeat == MONTHLY else None
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (chat_id, fires_at, message, repeat, device, days, kind, monthday,"
                " skip_holidays, stock_id, assignee, assignee_id, author_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (chat_id, when.isoformat(), message, repeat, device, stored_days, kind, monthday,
                 int(skip_holidays), stock_id, assignee, assignee_id, author_id),
            )
            return Job(
                id=cursor.lastrowid,
                chat_id=chat_id,
                when=when,
                message=message,
                repeat=repeat,
                device=device,
                days=stored_days,
                kind=kind,
                monthday=monthday,
                skip_holidays=skip_holidays,
                stock_id=stock_id,
                assignee=assignee,
                assignee_id=assignee_id,
                author_id=author_id,
            )

    def pending(self, chat_id: int | None = None) -> list[Job]:
        query = "SELECT * FROM jobs"
        params: tuple = ()
        if chat_id is not None:
            query += " WHERE chat_id = ?"
            params = (chat_id,)
        query += " ORDER BY fires_at ASC, id ASC"
        with self._connect() as conn:
            return [_row_to_job(row) for row in conn.execute(query, params)]

    def get(self, job_id: int) -> Job | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def remove(self, job_id: int) -> bool:
        with self._connect() as conn:
            return conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,)).rowcount > 0

    def update(
        self,
        job_id: int,
        when: datetime,
        message: str,
        repeat: str = ONCE,
        device: str | None = None,
        days: Iterable[int] | None = None,
        kind: str = ALARM,
        monthday: int | None = None,
        skip_holidays: bool = False,
        assignee: str | None = None,
        assignee_id: int | None = None,
    ) -> Job | None:
        """Reescribe un job conservando su id, su dueño y su autor; None si ya no existe.

        Sin `assignee` conserva la asignación que tenía.
        """
        stored_days = _validate(repeat, kind, days, monthday, skip_holidays)
        if assignee is not None:
            check_assignee(assignee, assignee_id)
        monthday = monthday if repeat == MONTHLY else None
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE jobs SET fires_at = ?, message = ?, repeat = ?, device = ?, days = ?,"
                " kind = ?, monthday = ?, skip_holidays = ?,"
                " assignee = COALESCE(?, assignee),"
                " assignee_id = CASE WHEN ? IS NULL THEN assignee_id ELSE ? END WHERE id = ?",
                (when.isoformat(), message, repeat, device, stored_days, kind, monthday,
                 int(skip_holidays), assignee, assignee, assignee_id, job_id),
            ).rowcount
        return self.get(job_id) if changed else None

    def reassign(self, person_id: int) -> int:
        """Pasa a «nadie» los jobs asignados a la persona; devuelve cuántos."""
        with self._connect() as conn:
            return conn.execute(
                f"UPDATE jobs SET assignee = '{NOBODY}', assignee_id = NULL"
                f" WHERE assignee = '{PERSON}' AND assignee_id = ?",
                (person_id,),
            ).rowcount

    def attach_stock(self, job_id: int, stock_id: int) -> bool:
        """Ata el job a un stock de remedio; False si el job ya no existe."""
        with self._connect() as conn:
            return conn.execute(
                "UPDATE jobs SET stock_id = ? WHERE id = ?", (stock_id, job_id)
            ).rowcount > 0

    def set_rota(self, job_id: int, names: Iterable[str] | None, start: date | None) -> bool:
        """Fija o quita los nombres que se turnan y desde qué lunes; False si el job no existe."""
        rota = ",".join(names) if names else None
        with self._connect() as conn:
            return conn.execute(
                "UPDATE jobs SET rota = ?, rota_from = ? WHERE id = ?",
                (rota, start.isoformat() if rota and start else None, job_id),
            ).rowcount > 0

    def reschedule(self, job_id: int, when: datetime) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET fires_at = ? WHERE id = ?", (when.isoformat(), job_id))

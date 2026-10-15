"""La pantalla de la casa en las teles: el kiosco a pedido y la vista de una alarma que suena."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from homeauto.quiet import away_of
from homeauto.schedule.store import ALARM, Job

log = logging.getLogger(__name__)

# El kiosco en solo lectura, que es lo único que se castea.
KIOSK_PATH = "/pantalla?ver=1"
# Cuánto después de que la alarma deja de sonar se cierra DashCast.
OFF_DELAY = timedelta(minutes=15)


def alarm_path(job_id: int) -> str:
    """La vista de una alarma que suena."""
    return f"/alarma?job={job_id}"


def off_key(alias: str) -> str:
    """La clave del timer que cierra DashCast en ese equipo."""
    return f"screen-off:{alias}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS screens (
    device TEXT PRIMARY KEY,
    job_id INTEGER NOT NULL,
    off_at TEXT
);
"""


class ScreenStore:
    """Qué alarma prendió cada tele y cuándo se cierra; `off_at` vacío es que sigue sonando."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def show(self, device: str, job_id: int) -> None:
        """Deja la tele mostrando esa alarma."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO screens (device, job_id, off_at) VALUES (?, ?, NULL) "
                "ON CONFLICT(device) DO UPDATE SET job_id = excluded.job_id, off_at = NULL",
                (device, job_id),
            )

    def job_for(self, device: str) -> int | None:
        """La alarma que suena en esa tele, o None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT job_id FROM screens WHERE device = ? AND off_at IS NULL", (device,)
            ).fetchone()
        return row["job_id"] if row else None

    def devices_of(self, job_id: int) -> list[str]:
        """Las teles donde suena esa alarma."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT device FROM screens WHERE job_id = ? AND off_at IS NULL ORDER BY device",
                (job_id,),
            ).fetchall()
        return [row["device"] for row in rows]

    def release(self, job_id: int, at: datetime) -> list[str]:
        """Fija el cierre de las teles de esa alarma y devuelve cuáles."""
        devices = self.devices_of(job_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE screens SET off_at = ? WHERE job_id = ? AND off_at IS NULL",
                (at.isoformat(), job_id),
            )
        return devices

    def all(self) -> list[tuple[str, int, datetime | None]]:
        """Cada tele con su alarma y su cierre."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM screens ORDER BY device").fetchall()
        return [
            (
                row["device"],
                row["job_id"],
                datetime.fromisoformat(row["off_at"]) if row["off_at"] else None,
            )
            for row in rows
        ]

    def off_at(self, device: str) -> datetime | None:
        """Cuándo se cierra esa tele, o None si no hay cierre pendiente."""
        with self._connect() as conn:
            row = conn.execute("SELECT off_at FROM screens WHERE device = ?", (device,)).fetchone()
        return datetime.fromisoformat(row["off_at"]) if row and row["off_at"] else None

    def clear(self, device: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM screens WHERE device = ?", (device,))


class ScreenPages:
    """Qué página va en cada tele: la vista de la alarma que suena o el kiosco."""

    def __init__(
        self,
        base: Callable[[], str],
        store: ScreenStore,
        quiet=None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        # La dirección de la API como la ve la tele: `http://ip:puerto`.
        self.base = base
        self.store = store
        self.quiet = quiet
        self.clock = clock

    def url(self, path: str) -> str:
        return f"{self.base()}{path}"

    def quiet_now(self) -> bool:
        return self.quiet is not None and bool(self.quiet.is_quiet(self.clock()))

    def away_now(self) -> bool:
        return away_of(self.quiet, self.clock())

    def restore_url(self, alias: str) -> str | None:
        """Lo que vuelve a la tele después de un anuncio; None en descanso o vacaciones."""
        if self.quiet_now():
            return None
        job_id = self.store.job_for(alias)
        return self.url(KIOSK_PATH if job_id is None else alarm_path(job_id))


class Screens:
    """Prende, restaura y cierra la pantalla de la casa en los equipos que la tienen."""

    def __init__(
        self,
        speakers,
        devices: Iterable[str],
        pages: ScreenPages,
        timer,
        fallback: str = "",
    ):
        self.speakers = speakers
        self.devices = {alias.strip().lower() for alias in devices}
        self.pages = pages
        self.store = pages.store
        # Lo mismo que espera `Reminders`: `schedule(key, when, action)` y `unschedule(key)`.
        self.timer = timer
        # El equipo de un job que no trae ninguno.
        self.fallback = fallback

    def is_screen(self, alias: str) -> bool:
        return alias.strip().lower() in self.devices

    def restore_url(self, alias: str) -> str | None:
        return self.pages.restore_url(alias)

    def show(self, alias: str) -> bool:
        """Muestra el kiosco a pedido; False en vacaciones. Ignora el descanso."""
        if self.pages.away_now():
            return False
        self._cancel_off(alias)
        self.speakers.get(alias).show(self.pages.url(KIOSK_PATH))
        return True

    def hide(self, alias: str) -> bool:
        """Cierra la pantalla si sigue siendo nuestra; False si no estaba."""
        self._cancel_off(alias)
        return self.speakers.get(alias).hide()

    def ring(self, job: Job) -> None:
        """Anota las teles de una alarma que empieza a sonar, si puede prenderlas."""
        if job.kind != ALARM or self.pages.quiet_now():
            return
        for alias in job.devices or [self.fallback]:
            if self.is_screen(alias):
                self.timer.unschedule(off_key(alias))
                self.store.show(alias, job.id)

    def light(self, job_id: int) -> None:
        """Muestra la vista de la alarma en sus teles; una tele apagada no la frena."""
        for alias in self.store.devices_of(job_id):
            try:
                self.speakers.get(alias).show(self.pages.url(alarm_path(job_id)))
            except Exception as exc:  # noqa: BLE001
                log.warning("could not show alarm %s on %s: %s", job_id, alias, exc)

    def rang(self, job_id: int) -> None:
        """La alarma dejó de sonar: agenda el cierre de sus teles."""
        at = self.pages.clock() + OFF_DELAY
        for alias in self.store.release(job_id, at):
            self._arm(alias, at)

    def start(self, now: datetime, ringing: Iterable[int] = ()) -> None:
        """Rearma los cierres tras un reinicio; los vencidos se cierran ya."""
        still = set(ringing)
        for alias, job_id, off_at in self.store.all():
            if off_at is None:
                if job_id in still:
                    continue
                off_at = now + OFF_DELAY
                self.store.release(job_id, off_at)
            if off_at <= now:
                self._off(alias)
            else:
                self._arm(alias, off_at)

    def _arm(self, alias: str, when: datetime) -> None:
        self.timer.schedule(off_key(alias), when, lambda: self._off(alias))

    def _cancel_off(self, alias: str) -> None:
        self.timer.unschedule(off_key(alias))
        self.store.clear(alias)

    def _off(self, alias: str) -> None:
        """Cierra DashCast en la tele, salvo que otra alarma la haya vuelto a prender."""
        if self.store.off_at(alias) is None:
            return
        self.store.clear(alias)
        try:
            self.speakers.get(alias).hide()
        except Exception as exc:  # noqa: BLE001
            log.warning("could not close the screen on %s: %s", alias, exc)

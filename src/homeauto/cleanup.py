"""El depurador: propone borrar lo que ya no sirve en la casa, y borra al confirmar."""

from __future__ import annotations

import calendar
import logging
import secrets
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from homeauto.config import Config
from homeauto.schedule.awaiting import KEEP
from homeauto.schedule.history import DONE, OFF, SNOOZE, Entry
from homeauto.schedule.reminders import SNOOZE_WINDOW
from homeauto.schedule.spec import repetition_label
from homeauto.schedule.store import ONCE, Job
from homeauto.tele import Tele, normalize

log = logging.getLogger(__name__)

TELES = "teles"
JOBS = "avisos"
HISTORY = "historial"
CACHE = "audio"
LISTS = "listas"

# Una tele sin latir hace más que esto ya no se usa.
TELE_UNSEEN = timedelta(days=7)
# Cuántas veces seguidas sin respuesta hacen inútil a un aviso que repite.
IGNORED_IN_A_ROW = 14
# Cuánto después de su hora un aviso de una sola vez ya no va a sonar.
OVERDUE = timedelta(days=1)
# Cuánto dura una vista previa antes de que haya que pedirla de nuevo.
PLAN_TTL = timedelta(minutes=10)
# Los meses de historial que se ofrecen conservar y el rango que se acepta.
HISTORY_MONTHS = (1, 3, 6, 12)
HISTORY_MIN_MONTHS = 1
HISTORY_MAX_MONTHS = 12
# Un audio del cache sin usar hace más que esto ya no se pide.
CACHE_UNUSED = timedelta(days=30)
# Lo terminado del cache: la voz y su nota de voz.
CACHED = (".wav", ".ogg")
# Un audio a medio hacer más viejo que esto ya no se termina.
PARTIAL_STALE = timedelta(hours=1)
# Un ítem de una lista agregado hace más que esto se propone sacar.
LIST_STALE = timedelta(days=30)

# Por qué se propone borrar una tele.
NOT_A_SCREEN = "no está en SCREEN_DEVICES"
UNSEEN = "sin latir hace más de siete días"

# Por qué se propone borrar un aviso.
OUTSIDER = "autor fuera de la lista"
GONE_DEVICE = "su equipo ya no existe"
IGNORED = f"las últimas {IGNORED_IN_A_ROW} veces nadie lo atendió"
STALE_ONCE = "de una sola vez y vencido hace más de un día"

# Lo que cuenta como que alguien atendió el aviso.
ANSWERED = (DONE, OFF, SNOOZE)


def months_ago(now: datetime, months: int) -> datetime:
    """El mismo día y hora `months` meses atrás, o el último día de ese mes si no lo tiene."""
    year, month = divmod(now.year * 12 + now.month - 1 - months, 12)
    month += 1
    day = min(now.day, calendar.monthrange(year, month)[1])
    return now.replace(year=year, month=month, day=day)


def tele_reason(tele: Tele, screen_devices: Iterable[str], now: datetime) -> str | None:
    """Por qué sobra la tele, o None si no sobra."""
    if normalize(tele.alias) not in {normalize(alias) for alias in screen_devices}:
        return NOT_A_SCREEN
    if tele.last_seen is None or now - tele.last_seen > TELE_UNSEEN:
        return UNSEEN
    return None


def ignored(entries: list[Entry]) -> bool:
    """Si las últimas veces que sonó alcanzan y ninguna tuvo respuesta."""
    return len(entries) >= IGNORED_IN_A_ROW and all(
        entry.closed not in ANSWERED for entry in entries[:IGNORED_IN_A_ROW]
    )


def job_reasons(
    job: Job,
    now: datetime,
    allowed: Iterable[int],
    devices: Iterable[str],
    entries: list[Entry],
) -> tuple[str, ...]:
    """Los motivos por los que sobra el aviso; vacío si no sobra."""
    allowed = frozenset(allowed)
    known = {alias.lower() for alias in devices}
    reasons = []
    if allowed and job.chat_id not in allowed:
        reasons.append(OUTSIDER)
    if job.devices and not any(alias.lower() in known for alias in job.devices):
        reasons.append(GONE_DEVICE)
    if job.repeat != ONCE and ignored(entries):
        reasons.append(IGNORED)
    if job.repeat == ONCE and now - job.when > OVERDUE:
        reasons.append(STALE_ONCE)
    return tuple(reasons)


@dataclass(frozen=True)
class TeleCandidate:
    alias: str
    reason: str
    version: str
    last_seen: datetime | None


@dataclass(frozen=True)
class JobCandidate:
    job: Job
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CacheFile:
    name: str
    size: int
    partial: bool


@dataclass(frozen=True)
class Overview:
    teles: int
    jobs: int
    leftovers: int
    history: int = 0
    cache: int = 0
    cache_bytes: int = 0
    lists: int = 0
    undated: int = 0


@dataclass(frozen=True)
class Plan:
    """Lo que se mostró para borrar, a nombre de un chat y con su vencimiento."""

    token: str
    chat_id: int
    category: str
    created: datetime
    teles: tuple[str, ...] = ()
    jobs: tuple[int, ...] = ()
    fired: tuple[int, ...] = ()
    waits: tuple[int, ...] = ()
    before: datetime | None = None
    rows: int = 0
    files: tuple[str, ...] = ()
    items: tuple[int, ...] = ()

    @property
    def size(self) -> int:
        return (
            len(self.teles) + len(self.jobs) + len(self.fired) + len(self.waits) + self.rows
            + len(self.files) + len(self.items)
        )


@dataclass(frozen=True)
class Preview:
    """La vista previa de una categoría: el texto y el token para confirmarla."""

    text: str
    token: str | None
    size: int
    teles: tuple[TeleCandidate, ...] = ()
    jobs: tuple[JobCandidate, ...] = ()
    fired: tuple[int, ...] = ()
    waits: tuple[int, ...] = ()
    files: tuple[str, ...] = ()
    items: tuple[tuple[int, str, str, datetime], ...] = ()


def _moment(when: datetime | None) -> str:
    return when.strftime("%d/%m %H:%M") if when is not None else "nunca"


def _tele_line(candidate: TeleCandidate) -> str:
    version = candidate.version or "sin versión"
    return (
        f"· {candidate.alias} — {candidate.reason} · {version}"
        f" · último latido {_moment(candidate.last_seen)}"
    )


def _job_line(candidate: JobCandidate) -> str:
    job = candidate.job
    repetition = repetition_label(job) or f"una vez, {_moment(job.when)}"
    return (
        f"· #{job.id} · {repetition} · chat {job.chat_id} — {job.message}"
        f" ({'; '.join(candidate.reasons)})"
    )


def _megabytes(size: int) -> str:
    return f"{size / 1_000_000:.1f}".replace(".", ",") + " MB"


def _months(months: int) -> str:
    return f"{months} mes" if months == 1 else f"{months} meses"


def overview_text(overview: Overview) -> str:
    """El conteo por categoría, o que no hay nada."""
    if not (
        overview.teles or overview.jobs or overview.leftovers or overview.history
        or overview.cache or overview.lists
    ):
        return "🧹 No hay nada para depurar."
    jobs = f"⏰ Avisos: {overview.jobs}"
    if overview.leftovers:
        jobs += f", más {overview.leftovers} restos de lo que ya sonó"
    lists = f"🛒 Listas: {overview.lists} de hace más de treinta días"
    if overview.undated:
        lists += f", y {overview.undated} sin fecha que no se tocan"
    return "\n".join([
        "🧹 Para depurar:",
        f"📺 Teles: {overview.teles}",
        jobs,
        f"📜 Historial: {overview.history} de hace más de un mes",
        f"🔊 Audio: {overview.cache} ({_megabytes(overview.cache_bytes)})",
        lists,
    ])


def _teles_text(teles: tuple[TeleCandidate, ...]) -> str:
    if not teles:
        return "📺 No hay teles para borrar."
    return "\n".join(["📺 Teles para borrar:", *(_tele_line(tele) for tele in teles)])


def _jobs_text(
    jobs: tuple[JobCandidate, ...], fired: tuple[int, ...], waits: tuple[int, ...]
) -> str:
    if not (jobs or fired or waits):
        return "⏰ No hay avisos para borrar."
    lines = ["⏰ Avisos para borrar:", *(_job_line(job) for job in jobs)]
    if fired or waits:
        lines.append(
            f"Y restos de lo que ya sonó: {len(fired)} para posponer vencidos"
            f" y {len(waits)} «Hecho» vencidos."
        )
    return "\n".join(lines)


def _history_text(months: int, before: datetime, rows: int) -> str:
    day = before.strftime("%d/%m/%Y")
    if not rows:
        return f"📜 No hay historial cerrado de antes del {day}."
    return (
        f"📜 Historial: dejo {_months(months)} y borro {rows} cerradas de antes del {day}."
        " Lo que sigue abierto queda."
    )


def _cache_text(files: tuple[CacheFile, ...]) -> str:
    if not files:
        return "🔊 No hay audio para borrar."
    partial = sum(1 for file in files if file.partial)
    size = _megabytes(sum(file.size for file in files))
    return (
        f"🔊 Audio para borrar: {len(files) - partial} audios sin usar hace más de treinta días"
        f" y {partial} a medio hacer, {size}."
    )


def _lists_text(items: tuple[tuple[int, str, str, datetime], ...], undated: int) -> str:
    if items:
        lines = ["🛒 De las listas, para sacar:"] + [
            f"· {name}: {item} (desde el {at.strftime('%d/%m')})" for _id, name, item, at in items
        ]
    else:
        lines = ["🛒 No hay ítems de hace más de treinta días."]
    if undated:
        lines.append(f"Hay {undated} sin fecha, de antes de que se anotara: esos no se tocan.")
    return "\n".join(lines)


def _done_text(deleted: int, shown: int) -> str:
    text = f"🧹 Borré {deleted} de {shown}."
    if deleted < shown:
        text += " El resto cambió desde que lo viste y quedó."
    return text


def _unused(path: Path, now: datetime) -> CacheFile | None:
    """El archivo si es un audio sin usar o uno a medio hacer que ya no termina; si no, None."""
    partial = ".partial" in path.suffixes
    if not partial and path.suffix not in CACHED:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    limit = PARTIAL_STALE if partial else CACHE_UNUSED
    if path.is_file() and now - datetime.fromtimestamp(stat.st_mtime) > limit:
        return CacheFile(path.name, stat.st_size, partial)
    return None


class Cleaner:
    """Arma la vista previa de cada categoría y borra lo que todavía sobra al confirmar."""

    def __init__(
        self,
        config: Config,
        reminders,
        history=None,
        fired=None,
        awaiting=None,
        ringing=None,
        screens=None,
        tele=None,
        lists=None,
        cache_dir: Path | str | None = None,
        clock: Callable[[], datetime] = datetime.now,
        token: Callable[[], str] = lambda: secrets.token_hex(4),
    ):
        self.config = config
        self.reminders = reminders
        self.history = history
        self.fired = fired
        self.awaiting = awaiting
        self.ringing = ringing
        # Qué alarma muestra cada tele; None sin API.
        self.screens = screens
        # El registro de las teles con su app; None sin API.
        self.tele = tele
        self.lists = lists
        # El cache de síntesis que sirve el MediaServer; None si no hay.
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.clock = clock
        self.token = token
        self._plans: dict[str, Plan] = {}
        self._lock = threading.Lock()

    # --- candidatos ---

    def _screen_rows(self) -> list[tuple[str, int, datetime | None]]:
        return self.screens.all() if self.screens is not None else []

    def _teles(self, now: datetime) -> tuple[TeleCandidate, ...]:
        if self.tele is None:
            return ()
        showing = {normalize(device) for device, _job, _off in self._screen_rows()}
        candidates = []
        for tele in self.tele.store.all():
            if tele.alias in showing or self.tele.alive(tele.alias):
                continue
            reason = tele_reason(tele, self.config.screen_devices, now)
            if reason is not None:
                candidates.append(
                    TeleCandidate(tele.alias, reason, tele.version_name, tele.last_seen)
                )
        return tuple(candidates)

    def _protected_jobs(self, now: datetime) -> set[int]:
        """Los avisos que no se tocan: suenan, están en una tele o sonaron hace menos de `SNOOZE_WINDOW`."""
        protected = {job_id for _device, job_id, _off in self._screen_rows()}
        if self.ringing is not None:
            protected |= {ringing.job_id for ringing in self.ringing.all()}
        if self.awaiting is not None:
            protected |= {
                wait.job_id
                for wait in self.awaiting.all()
                if now - wait.fired_at < SNOOZE_WINDOW
            }
        if self.fired is not None:
            protected |= {
                last.job_id
                for _chat, last in self.fired.all()
                if last.job_id is not None and now - last.at < SNOOZE_WINDOW
            }
        return protected

    def _jobs(self, now: datetime) -> tuple[JobCandidate, ...]:
        protected = self._protected_jobs(now)
        candidates = []
        for job in self.reminders.list(None):
            if job.id in protected or (job.repeat == ONCE and job.when > now):
                continue
            entries = self.history.latest(job.id, IGNORED_IN_A_ROW) if self.history else []
            if entries and now - entries[0].fired_at < SNOOZE_WINDOW:
                continue
            reasons = job_reasons(
                job, now, self.config.allowed_chat_ids, self.config.devices, entries
            )
            if reasons:
                candidates.append(JobCandidate(job, reasons))
        return tuple(candidates)

    def _stale_fired(self, now: datetime) -> tuple[int, ...]:
        if self.fired is None:
            return ()
        return tuple(chat for chat, last in self.fired.all() if now - last.at > SNOOZE_WINDOW)

    def _stale_waits(self, now: datetime, jobs: Iterable[int] = ()) -> tuple[int, ...]:
        """Las esperas vencidas, sin las de los avisos que ya se proponen borrar."""
        if self.awaiting is None:
            return ()
        skip = set(jobs)
        return tuple(
            wait.job_id
            for wait in self.awaiting.all()
            if now - wait.fired_at > KEEP and wait.job_id not in skip
        )

    def _history_count(self, before: datetime) -> int:
        return self.history.count_before(before) if self.history is not None else 0

    def _cache(self, now: datetime) -> tuple[CacheFile, ...]:
        """Los audios sin usar y los a medio hacer que ya no van a terminar."""
        if self.cache_dir is None:
            return ()
        try:
            paths = sorted(self.cache_dir.iterdir())
        except OSError:
            return ()
        return tuple(file for file in (_unused(path, now) for path in paths) if file)

    def _old_items(
        self, now: datetime, list_name: str | None = None
    ) -> tuple[tuple[int, str, str, datetime], ...]:
        if self.lists is None:
            return ()
        return tuple(self.lists.older_than(now - LIST_STALE, list_name))

    def _undated(self, list_name: str | None = None) -> int:
        return self.lists.undated(list_name) if self.lists is not None else 0

    # --- lo que ve el chat ---

    def overview(self) -> Overview:
        """Cuánto hay para depurar en cada categoría."""
        now = self.clock()
        jobs = self._jobs(now)
        waits = self._stale_waits(now, (c.job.id for c in jobs))
        files = self._cache(now)
        return Overview(
            teles=len(self._teles(now)),
            jobs=len(jobs),
            leftovers=len(self._stale_fired(now)) + len(waits),
            history=self._history_count(months_ago(now, HISTORY_MIN_MONTHS)),
            cache=len(files),
            cache_bytes=sum(file.size for file in files),
            lists=len(self._old_items(now)),
            undated=self._undated(),
        )

    def preview(
        self,
        chat_id: int,
        category: str,
        months: int | None = None,
        list_name: str | None = None,
    ) -> Preview:
        """El detalle de una categoría; si hay algo, guarda el plan con su token.

        `months` es cuánto historial se conserva y `list_name` acota las listas a una.
        """
        now = self.clock()
        if category == TELES:
            teles = self._teles(now)
            plan = Plan("", chat_id, category, now, teles=tuple(t.alias for t in teles))
            preview = Preview(_teles_text(teles), None, plan.size, teles=teles)
        elif category == JOBS:
            jobs, fired = self._jobs(now), self._stale_fired(now)
            waits = self._stale_waits(now, (c.job.id for c in jobs))
            plan = Plan(
                "", chat_id, category, now,
                jobs=tuple(c.job.id for c in jobs), fired=fired, waits=waits,
            )
            preview = Preview(
                _jobs_text(jobs, fired, waits), None, plan.size, jobs=jobs, fired=fired,
                waits=waits,
            )
        elif category == HISTORY:
            if months is None or not HISTORY_MIN_MONTHS <= months <= HISTORY_MAX_MONTHS:
                raise ValueError(f"meses fuera de rango: {months}")
            before = months_ago(now, months)
            rows = self._history_count(before)
            plan = Plan("", chat_id, category, now, before=before, rows=rows)
            preview = Preview(_history_text(months, before, rows), None, plan.size)
        elif category == CACHE:
            files = self._cache(now)
            plan = Plan("", chat_id, category, now, files=tuple(f.name for f in files))
            preview = Preview(_cache_text(files), None, plan.size, files=plan.files)
        elif category == LISTS:
            items = self._old_items(now, list_name)
            plan = Plan("", chat_id, category, now, items=tuple(item[0] for item in items))
            preview = Preview(
                _lists_text(items, self._undated(list_name)), None, plan.size, items=items
            )
        else:
            raise ValueError(f"categoría desconocida: {category}")
        if not plan.size:
            return preview
        token = self.token()
        with self._lock:
            self._prune(now)
            self._plans[token] = replace(plan, token=token)
        return replace(preview, token=token)

    def confirm(self, chat_id: int, token: str) -> str | None:
        """Borra lo mostrado que todavía sobra; None si el plan venció o no es de este chat."""
        now = self.clock()
        plan = self._take(chat_id, token, now)
        if plan is None:
            return None
        if plan.category == TELES:
            still = {candidate.alias for candidate in self._teles(now)}
            deleted = sum(
                self.tele.forget(alias) for alias in plan.teles if alias in still
            )
        elif plan.category == HISTORY:
            deleted = self.history.delete_before(plan.before, plan.created)
        elif plan.category == CACHE:
            deleted = self._purge_cache(plan, now)
        elif plan.category == LISTS:
            still = {item[0] for item in self._old_items(now)}
            deleted = self.lists.remove_old(
                (item for item in plan.items if item in still), now - LIST_STALE
            )
        else:
            deleted = self._purge_jobs(plan, now)
        log.info(
            "depurador: el chat %s borró %s de %s en %s", chat_id, deleted, plan.size, plan.category
        )
        return _done_text(deleted, plan.size)

    def drop(self, chat_id: int, token: str) -> bool:
        """Descarta el plan sin borrar nada; False si ya no estaba."""
        return self._take(chat_id, token, self.clock()) is not None

    # --- internos ---

    def _purge_jobs(self, plan: Plan, now: datetime) -> int:
        jobs = {candidate.job.id for candidate in self._jobs(now)}
        fired = set(self._stale_fired(now))
        waits = set(self._stale_waits(now, jobs))
        deleted = sum(
            self.reminders.cancel(None, job_id, any_owner=True)
            for job_id in plan.jobs
            if job_id in jobs
        )
        deleted += sum(
            self.fired.forget_before(chat, now - SNOOZE_WINDOW)
            for chat in plan.fired
            if chat in fired
        )
        deleted += sum(
            self.reminders.forget_wait(job_id, now - KEEP)
            for job_id in plan.waits
            if job_id in waits
        )
        return deleted

    def _purge_cache(self, plan: Plan, now: datetime) -> int:
        """Borra los audios mostrados que siguen sin usarse."""
        still = {file.name for file in self._cache(now)}
        deleted = 0
        for name in plan.files:
            path = self.cache_dir / name
            if name not in still or _unused(path, now) is None:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            deleted += 1
        return deleted

    def _take(self, chat_id: int, token: str, now: datetime) -> Plan | None:
        """Saca el plan si es de ese chat; None si no existe, es de otro o venció."""
        with self._lock:
            plan = self._plans.get(token)
            if plan is None or plan.chat_id != chat_id:
                return None
            del self._plans[token]
        if now - plan.created > PLAN_TTL:
            return None
        return plan

    def _prune(self, now: datetime) -> None:
        """Olvida los planes vencidos."""
        for token in [t for t, plan in self._plans.items() if now - plan.created > PLAN_TTL]:
            del self._plans[token]

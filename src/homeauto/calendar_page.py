"""La página del mes, en HTML de solo lectura: grilla compacta y lista día por día."""

from __future__ import annotations

import re
from datetime import date, datetime
from html import escape
from typing import Callable

from homeauto.schedule.history import HistoryStore
from homeauto.schedule.month import (
    ALARM_ITEM,
    REMINDER_ITEM,
    TIMER_ITEM,
    Item,
    MonthView,
    month_bounds,
    month_view,
)
from homeauto.schedule.store import Store

PATH = "/agenda"

MONTH_NAMES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
WEEKDAY_SHORT = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
WEEKDAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

KIND_ICONS = {ALARM_ITEM: "⏰", REMINDER_ITEM: "📌", TIMER_ITEM: "⏲️"}
KIND_NAMES = {ALARM_ITEM: "alarma", REMINDER_ITEM: "recordatorio", TIMER_ITEM: "timer"}

_MONTH = re.compile(r"(\d{4})-(\d{2})")

STYLE = """
body{font-family:system-ui,sans-serif;margin:0;padding:8px;color:#222;background:#fafafa}
h1{font-size:1.2rem;text-align:center;margin:4px 0 8px}
nav{display:flex;justify-content:space-between;margin-bottom:8px}
nav a{text-decoration:none;padding:4px 8px}
table{width:100%;border-collapse:collapse;table-layout:fixed}
th{font-size:.75rem;font-weight:normal;color:#666}
td{border:1px solid #ddd;vertical-align:top;height:3.2rem;padding:2px;font-size:.7rem;background:#fff}
td.out{background:#f0f0f0;color:#aaa}
td.today{outline:2px solid #2a6;outline-offset:-2px}
td b{display:block;font-size:.8rem}
h2{font-size:1rem;margin:16px 0 4px}
ul{list-style:none;margin:0;padding:0}
li{padding:4px 0;border-bottom:1px solid #eee}
li.past{color:#666}
.time{font-variant-numeric:tabular-nums;margin-right:4px}
.mark{font-size:.8rem;margin-left:4px;color:#555}
@media (min-width:700px){body{max-width:760px;margin:0 auto;padding:16px}
td{height:5rem;font-size:.85rem}h1{font-size:1.5rem}}
"""


def parse_month(text: str | None, today: date) -> tuple[int, int]:
    """El año y mes de `AAAA-MM`; el mes de `today` si no se entiende."""
    match = _MONTH.fullmatch(text or "")
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 1000 <= year <= 9998 and 1 <= month <= 12:
            return year, month
    return today.year, today.month


def _link(year: int, month: int) -> str:
    return f"{PATH}?m={year:04d}-{month:02d}"


def _counts(items: list[Item]) -> str:
    """Un ícono por tipo con cuántos hay ese día."""
    parts = []
    for kind in (ALARM_ITEM, REMINDER_ITEM, TIMER_ITEM):
        count = sum(1 for item in items if item.kind == kind)
        if count:
            parts.append(f"{KIND_ICONS[kind]}{count}")
    return " ".join(parts)


def _marks(item: Item) -> str:
    """Cómo terminó un aviso que ya sonó."""
    marks = []
    if item.done:
        marks.append(f"✅ {escape(item.done_by or '')}".rstrip())
    if item.nags:
        marks.append(f"🔔×{item.nags}")
    if item.snoozed:
        marks.append("💤 pospuesto")
    if item.cancelled:
        marks.append("✖️ cancelado")
    if item.silent:
        marks.append("⚠️ no sonó")
    return "".join(f'<span class="mark">{mark}</span>' for mark in marks)


def _grid(view: MonthView) -> str:
    head = "".join(f"<th>{name}</th>" for name in WEEKDAY_SHORT)
    rows = []
    for week in view.weeks:
        cells = []
        for day in week:
            classes = [] if day.in_month else ["out"]
            if day.today:
                classes.append("today")
            attribute = f' class="{" ".join(classes)}"' if classes else ""
            cells.append(f"<td{attribute}><b>{day.date.day}</b>{_counts(day.items)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _list(view: MonthView) -> str:
    if not view.days:
        return "<p>Nada programado ni sonado este mes.</p>"
    sections = []
    for day in view.days:
        entries = []
        for item in day.items:
            css = ' class="past"' if item.past else ""
            entries.append(
                f"<li{css}><span class=\"time\">{item.at:%H:%M}</span>"
                f"{KIND_ICONS[item.kind]} <small>{KIND_NAMES[item.kind]}</small> "
                f"{escape(item.message)}{_marks(item)}</li>"
            )
        title = f"{WEEKDAY_NAMES[day.date.weekday()]} {day.date.day}"
        sections.append(f"<h2>{title}</h2><ul>{''.join(entries)}</ul>")
    return "".join(sections)


def render(view: MonthView) -> str:
    """La página completa del mes."""
    title = f"{MONTH_NAMES[view.month - 1]} {view.year}"
    return (
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>Agenda — {title}</title><style>{STYLE}</style></head><body>"
        f"<h1>{title}</h1>"
        f"<nav><a href=\"{_link(*view.previous)}\">← anterior</a>"
        f"<a href=\"{_link(*view.following)}\">siguiente →</a></nav>"
        f"{_grid(view)}{_list(view)}</body></html>"
    )


class CalendarPage:
    """Arma la página de un mes leyendo lo agendado y el historial."""

    def __init__(
        self,
        store: Store,
        history: HistoryStore,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.store = store
        self.history = history
        self.clock = clock

    def html(self, month: str | None) -> str:
        """La página del mes `AAAA-MM`, o del actual si no se entiende."""
        now = self.clock()
        year, number = parse_month(month, now.date())
        start, end = month_bounds(year, number)
        entries = self.history.between(start, min(end, now))
        view = month_view(self.store.pending(), entries, year, number, now)
        return render(view)

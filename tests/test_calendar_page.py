"""La página del mes: HTML de solo lectura con lo programado y lo que sonó."""

import re
from datetime import date, datetime

from homeauto.calendar_page import CalendarPage, parse_month, render
from homeauto.schedule.history import HistoryStore
from homeauto.schedule.month import Item, month_view
from homeauto.schedule.store import DAILY, REMINDER, Store

NOW = datetime(2026, 10, 5, 12, 0)


def test_a_valid_month_is_read():
    assert parse_month("2026-03", date(2026, 10, 5)) == (2026, 3)


def test_an_invalid_month_falls_back_to_the_current_one():
    today = date(2026, 10, 5)
    for raw in (None, "", "2026-13", "2026-00", "marzo", "26-03", "2026-3", "0000-01", "9999-12"):
        assert parse_month(raw, today) == (2026, 10), raw


def test_the_page_names_the_month_and_links_its_neighbours():
    page = render(month_view([], [], 2026, 1, datetime(2026, 1, 15, 9, 0)))

    assert "enero 2026" in page
    assert 'href="/agenda?m=2025-12"' in page
    assert 'href="/agenda?m=2026-02"' in page


def test_the_grid_starts_on_monday():
    page = render(month_view([], [], 2026, 10, NOW))

    assert page.index(">lun<") < page.index(">dom<")


def test_the_page_has_no_javascript():
    page = render(month_view([], [], 2026, 10, NOW))

    assert "<script" not in page.lower()


def test_what_a_person_wrote_is_escaped():
    view = month_view([], [], 2026, 10, NOW)
    view.weeks[1][0].items.append(
        Item(at=NOW, kind="alarm", message="<script>alert(1)</script>", done=True, done_by="<b>x</b>")
    )

    page = render(view)

    assert "<script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;b&gt;x&lt;/b&gt;" in page


def test_the_list_shows_time_text_and_marks():
    view = month_view([], [], 2026, 10, NOW)
    items = view.weeks[0][3].items
    items.append(
        Item(at=datetime(2026, 10, 1, 8, 5), kind="reminder", message="la pastilla",
             past=True, done=True, done_by="Eze", nags=2)
    )
    items.append(Item(at=datetime(2026, 10, 1, 9, 0), kind="alarm", message="arriba",
                      past=True, snoozed=True))
    items.append(Item(at=datetime(2026, 10, 1, 10, 0), kind="timer", message="pizza",
                      past=True, cancelled=True))
    items.append(Item(at=datetime(2026, 10, 1, 11, 0), kind="alarm", message="mudo",
                      past=True, silent=True))

    page = render(view)

    assert "jueves 1" in page
    assert "08:05" in page and "la pastilla" in page
    assert "✅ Eze" in page
    assert "🔔×2" in page
    assert "pospuesto" in page
    assert "cancelado" in page
    assert "no sonó" in page


def test_the_kinds_are_told_apart():
    view = month_view([], [], 2026, 10, NOW)
    for hour, kind in ((8, "alarm"), (9, "reminder"), (10, "timer")):
        view.weeks[0][3].items.append(Item(at=datetime(2026, 10, 1, hour, 0), kind=kind, message=kind))

    page = render(view)

    assert "alarma" in page and "recordatorio" in page and "timer" in page


def test_the_page_is_mobile_first():
    page = render(month_view([], [], 2026, 10, NOW))

    assert 'name="viewport"' in page
    assert "@media" in page


def test_the_page_reads_the_store_and_the_history(tmp_path):
    store = Store(tmp_path / "jobs.db")
    history = HistoryStore(tmp_path / "jobs.db")
    store.add(42, datetime(2026, 10, 6, 21, 0), "la pastilla", repeat=DAILY, kind=REMINDER)
    history.record(7, 42, REMINDER, DAILY, "el colegio", datetime(2026, 10, 2, 7, 0))
    history.mark_announced(7)
    history.mark_done(7, datetime(2026, 10, 2, 7, 3), "Eze")

    page = CalendarPage(store=store, history=history, clock=lambda: NOW).html("2026-10")

    assert "la pastilla" in page
    assert "el colegio" in page
    assert "✅ Eze" in page
    assert len(re.findall("la pastilla", page)) == 26


def test_an_invalid_month_shows_the_current_one(tmp_path):
    store = Store(tmp_path / "jobs.db")
    history = HistoryStore(tmp_path / "jobs.db")

    page = CalendarPage(store=store, history=history, clock=lambda: NOW).html("cualquiera")

    assert "octubre 2026" in page

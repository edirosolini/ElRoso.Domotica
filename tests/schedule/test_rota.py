"""`turn_for()`: a quién le toca cada ocurrencia de un job que rota por semana."""

import sqlite3
from datetime import date, datetime

from homeauto.schedule.rota import turn_for, turn_in, with_turn
from homeauto.schedule.store import DAILY, REMINDER, WEEKLY, Job, Store

# Lunes 12 de octubre de 2026.
MONDAY = date(2026, 10, 12)


def job(rota="Cin,Die", rota_from=MONDAY, repeat=WEEKLY, days="1"):
    return Job(
        id=7, chat_id=42, when=datetime(2026, 10, 12, 20, 0), message="sacar la basura",
        repeat=repeat, days=days, kind=REMINDER, rota=rota, rota_from=rota_from,
    )


def test_a_job_without_rota_has_no_turn():
    assert turn_for(job(rota=None, rota_from=None), datetime(2026, 10, 12, 20, 0)) is None


def test_the_first_week_is_the_first_name():
    assert turn_for(job(), datetime(2026, 10, 12, 20, 0)) == "Cin"


def test_the_whole_iso_week_is_the_same_name():
    assert turn_for(job(), datetime(2026, 10, 18, 23, 59)) == "Cin"


def test_the_next_week_is_the_second_name():
    assert turn_for(job(), datetime(2026, 10, 19, 0, 0)) == "Die"


def test_with_two_names_the_third_week_goes_back_to_the_first():
    assert turn_for(job(), datetime(2026, 10, 26, 20, 0)) == "Cin"


def test_three_names_take_turns_in_order():
    rota = job(rota="Cin,Die,Ana")

    turns = [turn_for(rota, datetime(2026, 10, 12 + 7 * week, 20, 0)) for week in range(3)]

    assert turns == ["Cin", "Die", "Ana"]


def test_the_start_counts_from_the_monday_of_its_week():
    rota = job(rota_from=date(2026, 10, 15))

    assert turn_for(rota, datetime(2026, 10, 12, 8, 0)) == "Cin"
    assert turn_for(rota, datetime(2026, 10, 19, 8, 0)) == "Die"


def test_the_end_of_the_year_does_not_skip_a_turn():
    # 2026 tiene 53 semanas ISO: el número de semana vuelve a uno sin cambiar el orden.
    rota = job(rota_from=date(2026, 12, 21))

    turns = [
        turn_for(rota, datetime(2026, 12, 21, 20, 0)),
        turn_for(rota, datetime(2026, 12, 28, 20, 0)),
        turn_for(rota, datetime(2027, 1, 4, 20, 0)),
        turn_for(rota, datetime(2027, 1, 11, 20, 0)),
    ]

    assert turns == ["Cin", "Die", "Cin", "Die"]


def test_a_daily_job_changes_turn_with_the_week_not_the_day():
    rota = job(repeat=DAILY, days=None)

    assert turn_for(rota, datetime(2026, 10, 13, 20, 0)) == "Cin"
    assert turn_for(rota, datetime(2026, 10, 20, 20, 0)) == "Die"


def test_the_names_are_trimmed():
    assert job(rota=" Cin , Die ").turns == ["Cin", "Die"]


def test_the_message_says_whose_turn_it_is():
    assert with_turn("sacar la basura", "Cin") == "Le toca a Cin: sacar la basura"


def test_the_turn_can_be_read_back_from_the_message():
    assert turn_in("Le toca a Cin: sacar la basura") == "Cin"
    assert turn_in("sacar la basura") is None


def test_the_store_keeps_the_rota(tmp_path):
    store = Store(tmp_path / "jobs.db")
    added = store.add(42, datetime(2026, 10, 12, 20, 0), "sacar la basura",
                      repeat=WEEKLY, days=[1], kind=REMINDER)

    assert store.set_rota(added.id, ["Cin", "Die"], MONDAY)

    stored = store.get(added.id)
    assert stored.turns == ["Cin", "Die"]
    assert stored.rota_from == MONDAY


def test_the_store_removes_the_rota(tmp_path):
    store = Store(tmp_path / "jobs.db")
    added = store.add(42, datetime(2026, 10, 12, 20, 0), "sacar la basura",
                      repeat=WEEKLY, days=[1], kind=REMINDER)
    store.set_rota(added.id, ["Cin", "Die"], MONDAY)

    assert store.set_rota(added.id, None, None)

    stored = store.get(added.id)
    assert stored.rota is None and stored.rota_from is None


def test_setting_the_rota_of_a_missing_job_says_so(tmp_path):
    assert not Store(tmp_path / "jobs.db").set_rota(99, ["Cin"], MONDAY)


def test_updating_a_job_keeps_its_rota(tmp_path):
    store = Store(tmp_path / "jobs.db")
    added = store.add(42, datetime(2026, 10, 12, 20, 0), "sacar la basura",
                      repeat=WEEKLY, days=[1], kind=REMINDER)
    store.set_rota(added.id, ["Cin", "Die"], MONDAY)

    updated = store.update(added.id, datetime(2026, 10, 12, 21, 0), "sacar los residuos",
                           repeat=WEEKLY, days=[1, 4], kind=REMINDER)

    assert updated.turns == ["Cin", "Die"]
    assert updated.rota_from == MONDAY


def test_an_old_database_gets_the_rota_columns(tmp_path):
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,"
            " fires_at TEXT NOT NULL, message TEXT NOT NULL, repeat TEXT NOT NULL DEFAULT 'once')"
        )
        conn.execute(
            "INSERT INTO jobs (chat_id, fires_at, message) VALUES (42, ?, 'vieja')",
            (datetime(2026, 10, 12, 20, 0).isoformat(),),
        )

    old = Store(path).pending()[0]

    assert old.rota is None and old.rota_from is None
    assert turn_for(old, old.when) is None

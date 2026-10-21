"""El registro de las teles con su app y su latido."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from homeauto.tele import STALE, Tele, TeleLink, TeleStore

NOW = datetime(2026, 10, 21, 12, 0)


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


class CountingStore(TeleStore):
    """TeleStore de verdad que cuenta cuántas veces anota un latido."""

    def __init__(self, db_path):
        super().__init__(db_path)
        self.writes = 0

    def seen(self, alias, at, address):
        self.writes += 1
        super().seen(alias, at, address)


@pytest.fixture
def db(tmp_path):
    return tmp_path / "jobs.db"


@pytest.fixture
def clock():
    return Clock()


def columns(db):
    with sqlite3.connect(db) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(teles)")}


def test_the_store_creates_its_table(db):
    TeleStore(db)

    assert columns(db) == {"alias", "version_name", "version_code", "caps", "last_seen",
                           "address"}


def test_the_store_adds_the_columns_an_old_table_lacks(db):
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE teles (alias TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO teles (alias) VALUES ('comedor')")

    store = TeleStore(db)

    assert columns(db) == {"alias", "version_name", "version_code", "caps", "last_seen",
                           "address"}
    assert store.get("comedor") == Tele("comedor", "", 0, (), None, "")


def test_hello_saves_the_tele_and_a_second_hello_replaces_it(db, clock):
    link = TeleLink(TeleStore(db), clock=clock)

    link.hello("comedor", "1.0", 1, ["play"], "192.168.68.20")
    clock.advance(minutes=5)
    link.hello("comedor", "1.1", 2, ["play", "show"], "192.168.68.21")

    assert TeleStore(db).get("comedor") == Tele(
        "comedor", "1.1", 2, ("play", "show"), clock.now, "192.168.68.21"
    )
    assert [tele.alias for tele in TeleStore(db).all()] == ["comedor"]


def test_the_alias_is_normalized(db, clock):
    link = TeleLink(TeleStore(db), clock=clock)

    link.hello("  Comedor ", "1.0", 1, [], "")

    assert TeleStore(db).get("comedor") is not None
    assert link.alive("COMEDOR")
    assert link.beat(" Comedor", "")


def test_a_tele_is_alive_until_it_goes_stale(db, clock):
    link = TeleLink(TeleStore(db), clock=clock)
    link.hello("comedor", "1.0", 1, [], "")

    clock.advance(seconds=STALE.total_seconds() - 1)
    assert link.alive("comedor")

    clock.advance(seconds=1)
    assert not link.alive("comedor")


def test_a_beat_keeps_it_alive(db, clock):
    link = TeleLink(TeleStore(db), clock=clock)
    link.hello("comedor", "1.0", 1, [], "")

    clock.advance(minutes=2)
    link.beat("comedor", "")
    clock.advance(minutes=2)

    assert link.alive("comedor")


def test_an_unknown_tele_is_not_alive_and_its_beat_is_refused(db, clock):
    link = TeleLink(TeleStore(db), clock=clock)

    assert not link.alive("comedor")
    assert not link.beat("comedor", "")
    assert TeleStore(db).get("comedor") is None


def test_beats_in_a_row_write_to_disk_at_most_once_a_minute(db, clock):
    store = CountingStore(db)
    link = TeleLink(store, clock=clock)
    link.hello("comedor", "1.0", 1, [], "192.168.68.20")

    for _ in range(11):
        clock.advance(seconds=5)
        assert link.beat("comedor", "192.168.68.20")
    assert store.writes == 0

    clock.advance(seconds=5)
    link.beat("comedor", "192.168.68.21")
    assert store.writes == 1
    assert TeleStore(db).get("comedor").last_seen == clock.now
    assert TeleStore(db).get("comedor").address == "192.168.68.21"


def test_after_a_restart_the_last_beat_comes_from_disk(db, clock):
    TeleLink(TeleStore(db), clock=clock).hello("comedor", "1.0", 1, [], "")

    restarted = TeleLink(TeleStore(db), clock=clock)

    assert restarted.alive("comedor")
    assert restarted.beat("comedor", "")

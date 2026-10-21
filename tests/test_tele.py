"""El registro de las teles con su app y su latido."""

import sqlite3
import threading
from datetime import datetime, timedelta

import pytest

from homeauto.tele import KEEP_CLOSED, STALE, Tele, TeleLink, TeleStore

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


# --- el buzón de órdenes ---


@pytest.fixture
def link(db, clock):
    link = TeleLink(TeleStore(db), clock=clock)
    link.hello("comedor", "1.0", 1, ["play", "show"], "")
    return link


def test_each_order_gets_a_growing_seq_per_tele(link):
    first = link.send("comedor", "play", url="http://casa/a.wav", min_volume=90, seconds=3.0)
    second = link.send("Comedor ", "show", url="http://casa/alarma?job=7")

    assert 0 < first < second


def test_the_seq_keeps_growing_after_a_restart(db, clock, link):
    before = link.send("comedor", "show", url="http://casa/x")
    clock.advance(seconds=30)

    restarted = TeleLink(TeleStore(db), clock=clock)

    assert restarted.send("comedor", "show", url="http://casa/x") > before


def test_the_orders_wait_in_the_mailbox_until_received(link):
    play = link.send("comedor", "play", url="http://casa/a.wav", min_volume=90, seconds=3.0)
    show = link.send("comedor", "show", url="http://casa/alarma?job=7")

    expected = [
        {"seq": play, "kind": "play", "url": "http://casa/a.wav", "min_volume": 90,
         "seconds": 3.0},
        {"seq": show, "kind": "show", "url": "http://casa/alarma?job=7"},
    ]
    assert link.orders("comedor") == expected
    assert link.orders("comedor") == expected, "leerlas no las borra"

    assert link.ack("comedor", play, "received") is True
    assert [order["seq"] for order in link.orders("comedor")] == [show]


def test_an_order_closes_with_done_or_failed(link):
    done = link.send("comedor", "play", url="u", min_volume=None, seconds=None)
    failed = link.send("comedor", "play", url="u", min_volume=None, seconds=None)

    assert link.ack("comedor", done, "received")
    assert link.ack("comedor", done, "done")
    assert link.ack("comedor", failed, "failed")

    assert link.wait("comedor", done, ("done",), timeout=0) == "done"
    assert link.wait("comedor", failed, ("received",), timeout=0) == "failed"
    assert link.orders("comedor") == []
    assert link.ack("comedor", done, "received") is False, "cerrada no vuelve atrás"


def test_a_repeated_received_is_accepted_and_changes_nothing(link):
    seq = link.send("comedor", "play", url="u", min_volume=None, seconds=None)
    link.ack("comedor", seq, "received")

    assert link.ack("comedor", seq, "received") is True
    assert link.wait("comedor", seq, ("received",), timeout=0) == "received"


def test_how_an_order_ended_is_kept_for_a_while_after_new_orders(link):
    failed = link.send("comedor", "play", url="u", min_volume=None, seconds=None)
    link.ack("comedor", failed, "failed")
    link.send("comedor", "show", url="v")
    assert link.wait("comedor", failed, ("done",), timeout=0) == "failed"

    for _ in range(KEEP_CLOSED):
        link.cancel("comedor", link.send("comedor", "show", url="v"))
    link.send("comedor", "show", url="v")

    assert link.wait("comedor", failed, ("done",), timeout=0) == "cancelled", "ya se olvidó"
    assert link.ack("comedor", failed, "done") is False


def test_a_wait_without_an_ack_gives_up(link):
    seq = link.send("comedor", "play", url="u", min_volume=None, seconds=None)

    assert link.wait("comedor", seq, ("received",), timeout=0.01) is None


def test_a_wait_wakes_up_with_the_ack_from_another_thread(link):
    seq = link.send("comedor", "play", url="u", min_volume=None, seconds=None)
    threading.Timer(0.01, link.ack, ("comedor", seq, "received")).start()

    assert link.wait("comedor", seq, ("received",), timeout=5) == "received"


def test_a_late_ack_after_the_order_was_cancelled_does_not_revive_it(link):
    seq = link.send("comedor", "play", url="u", min_volume=None, seconds=None)

    link.cancel("comedor", seq)

    assert link.orders("comedor") == []
    assert link.ack("comedor", seq, "received") is False
    assert link.ack("comedor", seq, "done") is False
    assert link.wait("comedor", seq, ("received",), timeout=0) == "cancelled"


def test_stop_empties_the_mailbox_and_cancels_what_was_open(link):
    pending = link.send("comedor", "play", url="u", min_volume=None, seconds=None)
    playing = link.send("comedor", "play", url="v", min_volume=None, seconds=None)
    link.ack("comedor", playing, "received")

    stop = link.send("comedor", "stop")

    assert link.orders("comedor") == [{"seq": stop, "kind": "stop"}]
    assert link.wait("comedor", pending, ("received",), timeout=0) == "cancelled"
    assert link.wait("comedor", playing, ("done",), timeout=0) == "cancelled"
    assert link.ack("comedor", playing, "done") is False


def test_a_show_or_stop_closes_once_the_app_received_it(link):
    show = link.send("comedor", "show", url="u")
    link.ack("comedor", show, "received")
    assert link.wait("comedor", show, (), timeout=0) == "done"
    stop = link.send("comedor", "stop")
    link.ack("comedor", stop, "received")
    play = link.send("comedor", "play", url="v", min_volume=None, seconds=None)
    link.ack("comedor", play, "received")

    assert link.wait("comedor", stop, (), timeout=0) == "done"
    assert link.wait("comedor", play, ("received",), timeout=0) == "received"
    assert link.ack("comedor", stop, "done") is False


def test_a_hide_closes_once_the_app_received_it(link):
    hide = link.send("comedor", "hide")

    assert link.orders("comedor") == [{"seq": hide, "kind": "hide"}]
    link.ack("comedor", hide, "received")
    assert link.wait("comedor", hide, (), timeout=0) == "done"
    assert link.orders("comedor") == []


def test_shows_that_only_get_received_do_not_pile_up(link):
    for _ in range(KEEP_CLOSED * 3):
        link.ack("comedor", link.send("comedor", "show", url="u"), "received")

    assert len(link._orders["comedor"]) <= KEEP_CLOSED + 1


def test_an_ack_of_an_unknown_order_is_refused_and_of_an_unknown_tele_is_none(link):
    assert link.ack("comedor", 999, "received") is False
    assert link.ack("cocina", 1, "received") is None


def test_the_app_is_used_only_alive_and_with_the_cap(db, clock):
    link = TeleLink(TeleStore(db), clock=clock)
    link.hello("comedor", "1.0", 1, ["show"], "")
    link.hello("recamara", "1.0", 1, ["play"], "")

    assert not link.can("comedor", "play")
    assert link.can("comedor", "show")
    assert link.can("Recamara", "play")
    assert not link.can("habitacion", "play")

    clock.advance(seconds=STALE.total_seconds())
    assert not link.can("recamara", "play")


def test_after_a_restart_the_caps_come_from_disk(db, clock):
    TeleLink(TeleStore(db), clock=clock).hello("comedor", "1.0", 1, ["play"], "")

    assert TeleLink(TeleStore(db), clock=clock).can("comedor", "play")

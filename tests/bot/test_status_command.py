from datetime import datetime

from homeauto.bot.commands import Commands
from homeauto.watch.status import Status

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
NOW = datetime(2026, 8, 30, 10, 0)


class FakeMonitor:
    def __init__(self, picture=None):
        self.picture = picture if picture is not None else {}

    def snapshot(self):
        return self.picture


def build(monitor=None):
    return Commands(
        config=make_config(allowed={OWNER}),
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        monitor=monitor,
        clock=lambda: NOW,
    )


def status(name, up, detail="HTTP 200 en 0.12s"):
    return Status(name, up, 0, not up, detail, NOW)


def test_without_a_monitor_it_says_so():
    reply = build().status(OWNER)

    assert "vigil" in reply.lower() or "servicio" in reply.lower()


def test_before_the_first_round_it_says_so():
    reply = build(FakeMonitor({})).status(OWNER)

    assert "todavía" in reply.lower()


def test_it_lists_every_service():
    monitor = FakeMonitor({
        "landing": status("landing", True),
        "facturador": status("facturador", False, "HTTP 502"),
    })

    reply = build(monitor).status(OWNER)

    assert "landing" in reply and "facturador" in reply
    assert "502" in reply


def test_down_services_are_visible_at_a_glance():
    monitor = FakeMonitor({"facturador": status("facturador", False, "HTTP 502")})

    reply = build(monitor).status(OWNER)

    assert "🔴" in reply or "caído" in reply.lower()


def test_everything_healthy_reads_as_such():
    monitor = FakeMonitor({"landing": status("landing", True)})

    reply = build(monitor).status(OWNER)

    assert "🟢" in reply or "ok" in reply.lower()


def test_a_stranger_gets_nothing():
    monitor = FakeMonitor({"landing": status("landing", True)})

    reply = build(monitor).status(99)

    assert "landing" not in reply

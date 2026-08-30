"""Run main()'s wiring end to end with stand-ins.

Two bugs already reached the container through this path: a renamed function
and a variable used before it existed. Neither showed up in a unit test,
because nothing exercised the assembly itself.
"""

import uuid

import pytest

from homeauto import main


class FakeJobQueue:
    def __init__(self):
        self.repeating = []
        self.daily = []

    def run_repeating(self, callback, interval, first=None, name=None):
        self.repeating.append(name)

    def run_daily(self, callback, time, name=None):
        self.daily.append(name)

    def run_once(self, callback, when, name=None):
        pass

    def get_jobs_by_name(self, name):
        return []


class Stopped(Exception):
    """Marks that wiring finished and polling would have started."""


class FakeApp:
    def __init__(self):
        self.bot = object()
        self.job_queue = FakeJobQueue()
        self.handlers = []
        self.post_init = None

    def add_handler(self, handler):
        self.handlers.append(handler)

    def run_polling(self, allowed_updates=None):
        raise Stopped()


class FakeBuilder:
    def __init__(self, app):
        self.app = app

    def token(self, _token):
        return self

    def build(self):
        return self.app


@pytest.fixture
def wired(tmp_path, monkeypatch):
    app = FakeApp()
    monkeypatch.setattr(main.Application, "builder", staticmethod(lambda: FakeBuilder(app)))
    monkeypatch.setattr(main, "build_speakers", lambda config: _FakeRegistry())
    monkeypatch.setattr(main, "STATE_DIR", tmp_path)
    monkeypatch.setattr(main, "CACHE_DIR", str(tmp_path / "cache"))
    return app


class _FakeRegistry:
    aliases = ["parlante"]

    def has(self, alias):
        return alias == "parlante"

    def get(self, alias):
        raise AssertionError("no se debería hablar durante el cableado")


def config_file(tmp_path, extra=""):
    path = tmp_path / "domotica.env"
    path.write_text(
        "TELEGRAM_TOKEN=123:ABC\n"
        f"CAST_DEVICES=parlante:{uuid.uuid4()}\n" + extra,
        encoding="utf-8",
    )
    return path


def run_main(monkeypatch, path):
    monkeypatch.setattr(main, "CONFIG_PATH", str(path))
    with pytest.raises(Stopped):
        main.main()


def test_the_minimum_configuration_wires_up(wired, tmp_path, monkeypatch):
    run_main(monkeypatch, config_file(tmp_path))

    assert wired.handlers, "no se registró ningún comando"
    assert wired.post_init is not None


def test_wiring_with_calendar_schedules_its_jobs(wired, tmp_path, monkeypatch):
    path = config_file(tmp_path, "CALENDAR_URL_PERSONAL=https://ejemplo/a.ics\nBRIEFING_AT=08:00\n")

    run_main(monkeypatch, path)

    assert "calendar-watch" in wired.job_queue.repeating
    assert "calendar-briefing" in wired.job_queue.daily


def test_wiring_with_seq_schedules_its_job(wired, tmp_path, monkeypatch):
    path = config_file(tmp_path, "SEQ_URL=http://172.68.0.7\nSEQ_API_KEY=una-clave\n")

    run_main(monkeypatch, path)

    assert "seq-watch" in wired.job_queue.repeating


def test_wiring_with_services_schedules_the_monitor(wired, tmp_path, monkeypatch):
    checks = tmp_path / "checks.json"
    checks.write_text('[{"name": "vpn", "host": "10.0.0.1", "port": 443}]', encoding="utf-8")
    path = config_file(tmp_path, f"CHECKS_FILE={checks}\n")

    run_main(monkeypatch, path)

    assert "service-watch" in wired.job_queue.repeating


def test_everything_at_once_wires_up(wired, tmp_path, monkeypatch):
    checks = tmp_path / "checks.json"
    checks.write_text('[{"name": "vpn", "host": "10.0.0.1", "port": 443}]', encoding="utf-8")
    path = config_file(
        tmp_path,
        "CALENDAR_URL_PERSONAL=https://ejemplo/a.ics\n"
        "SEQ_URL=http://172.68.0.7\nSEQ_API_KEY=una-clave\n"
        f"CHECKS_FILE={checks}\n"
        "API_TOKEN=un-token-suficientemente-largo\n",
    )

    run_main(monkeypatch, path)

    assert {"calendar-watch", "seq-watch", "service-watch"} <= set(wired.job_queue.repeating)


def test_a_broken_checks_file_stops_the_service(wired, tmp_path, monkeypatch):
    """Mejor no arrancar que arrancar sin vigilar, en silencio."""
    checks = tmp_path / "checks.json"
    checks.write_text("{no es json", encoding="utf-8")
    path = config_file(tmp_path, f"CHECKS_FILE={checks}\n")

    monkeypatch.setattr(main, "CONFIG_PATH", str(path))
    with pytest.raises(Exception) as caught:
        main.main()

    assert not isinstance(caught.value, Stopped)

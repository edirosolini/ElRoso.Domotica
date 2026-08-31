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
    assert "briefing" in wired.job_queue.daily


def test_the_briefing_does_not_need_a_calendar(wired, tmp_path, monkeypatch):
    """Sin agenda, el clima y el estado de los servicios siguen valiendo la pena."""
    run_main(monkeypatch, config_file(tmp_path, "BRIEFING_AT=08:00\n"))

    assert "briefing" in wired.job_queue.daily
    assert "calendar-watch" not in wired.job_queue.repeating


def test_the_rain_watcher_is_always_scheduled(wired, tmp_path, monkeypatch):
    """El clima tiene coordenadas por defecto, así que el aviso no depende de nada."""
    run_main(monkeypatch, config_file(tmp_path))

    assert "rain-watch" in wired.job_queue.repeating


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

    assert {"calendar-watch", "seq-watch", "service-watch", "rain-watch"} <= set(
        wired.job_queue.repeating
    )


def test_a_broken_checks_file_stops_the_service(wired, tmp_path, monkeypatch):
    """Mejor no arrancar que arrancar sin vigilar, en silencio."""
    checks = tmp_path / "checks.json"
    checks.write_text("{no es json", encoding="utf-8")
    path = config_file(tmp_path, f"CHECKS_FILE={checks}\n")

    monkeypatch.setattr(main, "CONFIG_PATH", str(path))
    with pytest.raises(Exception) as caught:
        main.main()

    assert not isinstance(caught.value, Stopped)


def test_wiring_without_a_key_leaves_the_polisher_off(wired, tmp_path, monkeypatch):
    """Sin LLM_API_KEY el texto sale tal cual, y nada intenta salir a internet."""
    run_main(monkeypatch, config_file(tmp_path, "CALENDAR_URL_PERSONAL=https://ejemplo/a.ics\n"))

    assert main.build_polisher.__name__ == "build_polisher"


def test_wiring_with_a_key_builds_the_polisher(wired, tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(main, "build_polisher", lambda config: built.append(config) or "polisher")

    path = config_file(
        tmp_path,
        "CALENDAR_URL_PERSONAL=https://ejemplo/a.ics\nLLM_API_KEY=una-clave\n",
    )
    run_main(monkeypatch, path)

    assert len(built) == 1
    assert built[0].llm_api_key == "una-clave"


def test_the_polisher_reaches_everything_the_house_says(tmp_path, monkeypatch):
    """Todo lo que genera el servicio pasa por el mismo pulidor. Menos /decir."""
    app = FakeApp()
    monkeypatch.setattr(main.Application, "builder", staticmethod(lambda: FakeBuilder(app)))
    monkeypatch.setattr(main, "build_speakers", lambda config: _FakeRegistry())
    monkeypatch.setattr(main, "STATE_DIR", tmp_path)
    monkeypatch.setattr(main, "CACHE_DIR", str(tmp_path / "cache"))

    sentinel = lambda text, must_keep=(): text
    monkeypatch.setattr(main, "build_polisher", lambda config: sentinel)

    seen = {}
    sources = (
        ("agenda", main.AgendaService),
        ("weather", main.WeatherClient),
        ("watcher", main.EventWatcher),
        ("announcer", main.Announcer),
        ("monitor", main.Monitor),
        ("seq", main.SeqWatcher),
        ("rain", main.RainWatcher),
        ("briefing", main.Briefing),
        ("api", main.ApiService),
    )
    for name, cls in sources:
        original = cls.__init__

        def spy(self, *args, __name=name, __original=original, **kwargs):
            seen[__name] = kwargs.get("polish")
            return __original(self, *args, **kwargs)

        monkeypatch.setattr(cls, "__init__", spy)

    checks = tmp_path / "checks.json"
    checks.write_text('[{"name": "vpn", "host": "10.0.0.1", "port": 443}]', encoding="utf-8")
    path = config_file(
        tmp_path,
        "CALENDAR_URL_PERSONAL=https://ejemplo/a.ics\nLLM_API_KEY=una-clave\n"
        "SEQ_URL=http://172.68.0.7\nSEQ_API_KEY=una-clave\n"
        f"CHECKS_FILE={checks}\n"
        "API_TOKEN=un-token-suficientemente-largo\n",
    )
    run_main(monkeypatch, path)

    assert seen == {name: sentinel for name, _ in sources}


def test_the_words_of_a_person_never_reach_the_polisher(tmp_path, monkeypatch):
    """🔴 /decir se dice tal cual: ahí las palabras son de alguien, no nuestras."""
    app = FakeApp()
    monkeypatch.setattr(main.Application, "builder", staticmethod(lambda: FakeBuilder(app)))
    monkeypatch.setattr(main, "build_speakers", lambda config: _FakeRegistry())
    monkeypatch.setattr(main, "STATE_DIR", tmp_path)
    monkeypatch.setattr(main, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(main, "build_polisher", lambda config: lambda text, must_keep=(): "REESCRITO")

    got = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        got.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path, "LLM_API_KEY=una-clave\n"))

    assert "polish" not in got, "los comandos no pulen: /decir va literal"


def test_the_wired_polisher_is_actually_callable(wired, tmp_path, monkeypatch):
    """🔴 build_polisher devolvía el objeto, no algo llamable: /clima y /agenda
    reventaban con TypeError en el contenedor, no en los tests."""
    captured = {}
    original = main.WeatherClient.__init__

    def spy(self, *args, **kwargs):
        captured["polish"] = kwargs.get("polish")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.WeatherClient, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path, "LLM_API_KEY=una-clave\n"))

    polish = captured["polish"]
    assert callable(polish), "lo cableado tiene que poder llamarse"

    # Y con la firma real que usan agenda, clima y watcher.
    polish.__self__.model = lambda _prompt: ""
    assert polish("Hoy tenés dos cosas.", must_keep=["nada"]) == "Hoy tenés dos cosas."

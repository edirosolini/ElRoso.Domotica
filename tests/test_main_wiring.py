"""Run main()'s wiring end to end with stand-ins.

Two bugs already reached the container through this path: a renamed function
and a variable used before it existed. Neither showed up in a unit test,
because nothing exercised the assembly itself.
"""

import json
import uuid
from datetime import datetime, timedelta

import pytest

from homeauto import main, polish
from homeauto.meals import DINNER, LUNCH, Meal
from homeauto.tele import Tele
from homeauto.web.app import Request


class FakeJobQueue:
    def __init__(self):
        self.repeating = []
        self.daily = []
        self.days = {}
        self.times = {}
        self.callbacks = {}
        self.once = []

    def run_repeating(self, callback, interval, first=None, name=None):
        self.repeating.append(name)
        self.callbacks[name] = callback

    def run_daily(self, callback, time, days=(0, 1, 2, 3, 4, 5, 6), name=None):
        self.daily.append(name)
        self.days[name] = days
        self.times[name] = time
        self.callbacks[name] = callback

    def run_once(self, callback, when, name=None):
        self.once.append(name)
        self.callbacks[name] = callback

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
    monkeypatch.setattr(
        main, "build_speakers", lambda config, synth=None, restore=None, tele=None: _FakeRegistry()
    )
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


def test_without_a_key_there_is_nobody_to_ask(wired, tmp_path, monkeypatch):
    """Sin LLM_API_KEY el comando tiene que contestar que no está configurado."""
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["asker"] = kwargs.get("asker")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path))

    assert seen["asker"] is None


def test_with_a_key_the_asker_is_wired_and_searches(wired, tmp_path, monkeypatch):
    """🔴 El que contesta preguntas busca; el que pule la redacción no."""
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["asker"] = kwargs.get("asker")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path, "LLM_API_KEY=una-clave\n"))

    asker = seen["asker"]
    assert asker is not None
    assert asker.model.search is True, "sin búsqueda contesta de memoria"
    assert asker.model.timeout > 6, "una búsqueda no entra en el timeout del pulido"


def test_free_text_is_only_understood_with_a_key(wired, tmp_path, monkeypatch):
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["router"] = kwargs.get("router")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path))

    assert seen["router"] is None


def test_the_router_uses_the_cheap_model_and_does_not_search(wired, tmp_path, monkeypatch):
    """🔴 Clasificar no es averiguar: buscar acá pagaría treinta segundos por mensaje."""
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["router"] = kwargs.get("router")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    path = config_file(tmp_path, "LLM_API_KEY=una-clave\nLLM_MODEL=barato\nASK_MODEL=caro\n")
    run_main(monkeypatch, path)

    router = seen["router"]
    assert router is not None
    assert router.model.search is False
    assert router.model.model == "barato", "el que interpreta es el rápido, no el que busca"


def test_a_message_without_a_slash_gets_a_handler(wired, tmp_path, monkeypatch):
    run_main(monkeypatch, config_file(tmp_path, "LLM_API_KEY=una-clave\n"))

    kinds = [type(handler).__name__ for handler in wired.handlers]
    assert "MessageHandler" in kinds, "el texto libre no tiene quién lo atienda"


def test_each_seq_instance_gets_its_own_job(wired, tmp_path, monkeypatch):
    """Dos VPS, dos Seq, dos jobs: un nombre repetido dejaría uno sin agendar."""
    path = config_file(
        tmp_path,
        "SEQ_URL_HOSTING=http://172.68.1.7\nSEQ_API_KEY_HOSTING=una\n"
        "SEQ_URL_NUBE=http://172.68.2.7\nSEQ_API_KEY_NUBE=otra\n",
    )

    run_main(monkeypatch, path)

    assert "seq-watch-hosting" in wired.job_queue.repeating
    assert "seq-watch-nube" in wired.job_queue.repeating


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
    monkeypatch.setattr(
        main, "build_speakers", lambda config, synth=None, restore=None, tele=None: _FakeRegistry()
    )
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
        ("closing", main.Closing),
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


def test_the_commands_get_both_the_polisher_and_the_corrector(tmp_path, monkeypatch):
    """Dos caminos y no uno: lo que genera la casa se pule, lo que escriben se corrige.

    Que `/decir` no pase por el pulidor se prueba donde se puede ver hablar, en
    `tests/bot/test_call_command.py`; acá se prueba que las dos piezas llegan.
    """
    app = FakeApp()
    monkeypatch.setattr(main.Application, "builder", staticmethod(lambda: FakeBuilder(app)))
    monkeypatch.setattr(
        main, "build_speakers", lambda config, synth=None, restore=None, tele=None: _FakeRegistry()
    )
    monkeypatch.setattr(main, "STATE_DIR", tmp_path)
    monkeypatch.setattr(main, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        main, "build_polisher", lambda config: lambda text, must_keep=(): "REESCRITO"
    )

    got = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        got.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path, "LLM_API_KEY=una-clave\n"))

    assert got["polish"]("lo que sea") == "REESCRITO"
    assert callable(got["correct"])


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


def test_the_conversation_is_wired_and_usable(wired, tmp_path, monkeypatch):
    """🔴 El doble tiene que servir para lo que sirve el real.

    Acá el real es barato de armar, así que se usa el que quedó cableado: se le
    guarda un pendiente y se lo vuelve a leer. Un centinela que solo viaja hasta
    su lugar no habría visto una tabla que no se crea.
    """
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["conversation"] = kwargs.get("conversation")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path))

    talk = seen["conversation"]
    assert talk is not None
    talk.remember(7, "alarma", "creá una alarma", ("hora",))
    assert talk.get(7).command == "alarma"


def test_the_conversation_shares_the_one_database(wired, tmp_path, monkeypatch):
    """Séptima tabla del mismo archivo, no una base aparte."""
    run_main(monkeypatch, config_file(tmp_path))

    import sqlite3

    with sqlite3.connect(tmp_path / "jobs.db") as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "pending" in tables


def test_wiring_without_a_key_leaves_the_text_as_typed(wired, tmp_path, monkeypatch):
    from homeauto.correct import as_written

    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["correct"] = kwargs.get("correct")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path))

    assert seen["correct"] is as_written


def test_the_wired_corrector_is_actually_callable(wired, tmp_path, monkeypatch):
    """🔴 Un `Corrector` no es llamable; ya se desplegó ese bug con el pulidor.

    El servicio arrancaba perfecto y reventaba con TypeError recién cuando
    alguien hablaba.
    """
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["correct"] = kwargs.get("correct")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    monkeypatch.setattr(main, "GoogleModel", lambda **kwargs: (lambda prompt: "Hola."))
    run_main(monkeypatch, config_file(tmp_path, "LLM_API_KEY=una-clave\n"))

    assert seen["correct"]("hola") == "Hola."


def test_the_wired_corrector_refuses_a_rewrite(wired, tmp_path, monkeypatch):
    """No alcanza con que sea llamable: tiene que traer puesta la validación.

    Un modelo que contesta otra cosa no puede llegar al parlante ni siquiera
    cableado de verdad; el pulidor sí puede, y son dos caminos distintos.
    """
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["correct"] = kwargs.get("correct")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    monkeypatch.setattr(main, "GoogleModel", lambda **kwargs: (lambda prompt: "Buenas tardes."))
    run_main(monkeypatch, config_file(tmp_path, "LLM_API_KEY=una-clave\n"))

    assert seen["correct"]("hola") == "hola"


# --- economía y noticias en el resumen --------------------------------------


def briefing_built(monkeypatch):
    """Lo que main() le pasó al resumen de la mañana."""
    seen = {}
    original = main.Briefing.__init__

    def spy(self, *args, **kwargs):
        seen.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Briefing, "__init__", spy)
    return seen


def test_the_economy_reaches_the_briefing(wired, tmp_path, monkeypatch):
    seen = briefing_built(monkeypatch)

    run_main(monkeypatch, config_file(tmp_path, "BRIEFING_AT=08:00\n"))

    assert seen["economy"] is not None
    assert seen["economy"].spoken, "el doble tiene que poder usarse como lo real"


def test_the_economy_can_be_turned_off(wired, tmp_path, monkeypatch):
    seen = briefing_built(monkeypatch)

    run_main(monkeypatch, config_file(tmp_path, "ECONOMY=off\n"))

    assert seen["economy"] is None


def test_the_verse_of_the_day_reaches_the_briefing(wired, tmp_path, monkeypatch):
    seen = briefing_built(monkeypatch)

    run_main(monkeypatch, config_file(tmp_path))

    assert seen["verse"] is not None
    assert seen["verse"].passage, "el doble tiene que poder usarse como lo real"


def test_the_verse_of_the_day_can_be_turned_off(wired, tmp_path, monkeypatch):
    seen = briefing_built(monkeypatch)

    run_main(monkeypatch, config_file(tmp_path, "VERSE=off\n"))

    assert seen["verse"] is None


def test_without_feeds_there_are_no_news(wired, tmp_path, monkeypatch):
    seen = briefing_built(monkeypatch)

    run_main(monkeypatch, config_file(tmp_path))

    assert seen["news"] is None


def test_the_feeds_reach_the_briefing(wired, tmp_path, monkeypatch):
    seen = briefing_built(monkeypatch)

    run_main(
        monkeypatch,
        config_file(tmp_path, "NEWS_RSS_INFOBAE=https://infobae/rss\nNEWS_COUNT=3\n"),
    )

    news = seen["news"]
    assert news is not None
    assert news.feeds == {"infobae": "https://infobae/rss"}
    assert news.count == 3


def test_the_other_warnings_of_the_sky_are_scheduled(wired, tmp_path, monkeypatch):
    """Calor, frío, viento y tormenta: no dependen de configurar nada."""
    run_main(monkeypatch, config_file(tmp_path))

    assert "sky-watch" in wired.job_queue.repeating


def test_the_sky_watcher_gets_a_usable_air_client(wired, tmp_path, monkeypatch):
    seen = _spy_init(monkeypatch, main.WeatherWatcher)
    run_main(monkeypatch, config_file(tmp_path))

    air = seen["air"]
    air.fetch = lambda latitude, longitude: {
        "hourly": {"time": ["2026-10-15T12:00"], "us_aqi": [130], "pm2_5": [40.0]}
    }

    assert air.worst_today(datetime(2026, 10, 15, 9, 0)) == 130


def test_without_a_key_nobody_listens_to_an_audio(wired, tmp_path, monkeypatch):
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["transcribe"] = kwargs.get("transcribe")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path))

    assert seen["transcribe"] is None


def test_the_transcriber_is_wired_with_the_cheap_model(wired, tmp_path, monkeypatch):
    """Transcribir no es averiguar: el que escucha es el rápido, sin búsqueda."""
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["transcribe"] = kwargs.get("transcribe")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    path = config_file(tmp_path, "LLM_API_KEY=una-clave\nLLM_MODEL=barato\nASK_MODEL=caro\n")
    run_main(monkeypatch, path)

    transcribe = seen["transcribe"]
    assert transcribe is not None
    assert callable(transcribe), "el doble tiene que poder usarse como lo real"
    assert transcribe.model.model == "barato"
    assert transcribe.model.search is False
    # 🔴 Subir el audio tarda más que pedir una reescritura: con los seis
    # segundos del pulidor, una nota de voz de unos pocos segundos ya da
    # timeout. Medido contra el endpoint real.
    assert transcribe.model.timeout == main.LISTEN_TIMEOUT > polish.TIMEOUT


# --- el proveedor del texto ---

ANTHROPIC_ENV = "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\n"


def _commands_kwargs(monkeypatch):
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    return seen


def test_with_anthropic_the_text_goes_to_claude(wired, tmp_path, monkeypatch):
    """Pulido, router, corrección y traducción con el barato; preguntas con el que busca."""
    from homeauto.claude import ClaudeModel

    seen = _commands_kwargs(monkeypatch)
    path = config_file(
        tmp_path,
        ANTHROPIC_ENV + "ANTHROPIC_MODEL=barato\nANTHROPIC_ASK_MODEL=caro\nLLM_API_KEY=k\n",
    )
    run_main(monkeypatch, path)

    cheap = {
        "pulido": seen["polish"].__self__.model,
        "router": seen["router"].model,
        "traducción": seen["translator"].model,
        "corrección": seen["correct"].__self__.model,
    }
    for name, model in cheap.items():
        assert isinstance(model, ClaudeModel), name
        assert model.model == "barato", name
        assert model.search is False, name
        assert model.effort == "low", name

    asker = seen["asker"].model
    assert isinstance(asker, ClaudeModel)
    assert asker.model == "caro"
    assert asker.search is True
    assert asker.effort == "medium"
    assert asker.timeout == main.ASK_TIMEOUT


def test_with_anthropic_the_voice_notes_stay_on_gemini(wired, tmp_path, monkeypatch):
    """Claude no acepta audio: transcribir sigue en Google."""
    seen = _commands_kwargs(monkeypatch)
    path = config_file(tmp_path, ANTHROPIC_ENV + "LLM_API_KEY=k\nLLM_MODEL=gemini-barato\n")
    run_main(monkeypatch, path)

    transcribe = seen["transcribe"]
    assert isinstance(transcribe.model, polish.GoogleModel)
    assert transcribe.model.model == "gemini-barato"
    assert transcribe.model.timeout == main.LISTEN_TIMEOUT


def test_with_anthropic_and_no_google_key_only_the_voice_notes_are_off(
    wired, tmp_path, monkeypatch
):
    seen = _commands_kwargs(monkeypatch)
    run_main(monkeypatch, config_file(tmp_path, ANTHROPIC_ENV))

    assert seen["transcribe"] is None
    assert seen["router"] is not None
    assert seen["asker"] is not None
    assert seen["translator"] is not None
    assert seen["polish"] is not polish.as_is


def test_the_wired_claude_model_is_usable(wired, tmp_path, monkeypatch):
    """El doble del SDK contesta como el real y la respuesta llega al pulidor."""
    from types import SimpleNamespace

    from homeauto import claude

    class FakeClient:
        def __init__(self):
            self.messages = self

        def create(self, **kwargs):
            block = SimpleNamespace(type="text", text="Hoy tenés dos cosas, che.")
            return SimpleNamespace(content=[block], stop_reason="end_turn")

    seen = _commands_kwargs(monkeypatch)
    run_main(monkeypatch, config_file(tmp_path, ANTHROPIC_ENV))

    model = seen["polish"].__self__.model
    assert model.make_client is claude.anthropic_client
    model.make_client = lambda api_key, timeout: FakeClient()
    assert seen["polish"]("Hoy tenés dos cosas.") == "Hoy tenés dos cosas, che."


def test_with_google_every_text_builder_stays_on_gemini(wired, tmp_path, monkeypatch):
    seen = _commands_kwargs(monkeypatch)
    path = config_file(tmp_path, "LLM_API_KEY=k\nLLM_MODEL=barato\nASK_MODEL=caro\n")
    run_main(monkeypatch, path)

    for model in (
        seen["polish"].__self__.model,
        seen["router"].model,
        seen["translator"].model,
        seen["correct"].__self__.model,
    ):
        assert isinstance(model, polish.GoogleModel)
        assert model.model == "barato"
        assert model.search is False
        assert model.timeout in (polish.TIMEOUT, main.TRANSLATE_TIMEOUT)
    assert isinstance(seen["asker"].model, polish.GoogleModel)
    assert seen["asker"].model.model == "caro"
    assert isinstance(seen["transcribe"].model, polish.GoogleModel)


def _text_models(seen):
    """Los modelos del pulido, el router, la traducción y la corrección."""
    return {
        "pulido": seen["polish"].__self__.model,
        "router": seen["router"].model,
        "traducción": seen["translator"].model,
        "corrección": seen["correct"].__self__.model,
    }


def test_the_questions_go_to_claude_while_the_text_stays_on_gemini(
    wired, tmp_path, monkeypatch
):
    from homeauto.claude import ClaudeModel

    seen = _commands_kwargs(monkeypatch)
    path = config_file(
        tmp_path,
        "LLM_API_KEY=k\nLLM_MODEL=barato\nASK_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\n",
    )
    run_main(monkeypatch, path)

    for name, model in _text_models(seen).items():
        assert isinstance(model, polish.GoogleModel), name
        assert model.model == "barato", name
    asker = seen["asker"].model
    assert isinstance(asker, ClaudeModel)
    assert asker.model == "claude-sonnet-5-5"
    assert asker.search is True
    assert asker.effort == "medium"
    assert asker.timeout == main.ASK_TIMEOUT


def test_the_questions_go_to_gemini_while_the_text_is_on_claude(wired, tmp_path, monkeypatch):
    from homeauto.claude import ClaudeModel

    seen = _commands_kwargs(monkeypatch)
    path = config_file(
        tmp_path, ANTHROPIC_ENV + "ASK_PROVIDER=google\nLLM_API_KEY=k\nASK_MODEL=caro\n"
    )
    run_main(monkeypatch, path)

    for name, model in _text_models(seen).items():
        assert isinstance(model, ClaudeModel), name
        assert model.model == "claude-haiku-5-5", name
    asker = seen["asker"].model
    assert isinstance(asker, polish.GoogleModel)
    assert asker.model == "caro"
    assert asker.search is True
    assert asker.timeout == main.ASK_TIMEOUT


def test_asking_google_without_its_key_leaves_only_the_questions_off(
    wired, tmp_path, monkeypatch
):
    seen = _commands_kwargs(monkeypatch)
    run_main(monkeypatch, config_file(tmp_path, ANTHROPIC_ENV + "ASK_PROVIDER=google\n"))

    assert seen["asker"] is None
    assert seen["router"] is not None
    assert seen["polish"] is not polish.as_is


def test_without_a_google_key_the_questions_still_go_to_claude(
    wired, tmp_path, monkeypatch, caplog
):
    caplog.set_level("INFO", logger="homeauto")
    seen = _commands_kwargs(monkeypatch)
    path = config_file(tmp_path, "ASK_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\n")
    run_main(monkeypatch, path)

    assert seen["polish"] is polish.as_is
    assert seen["router"] is None
    assert seen["asker"] is not None
    assert "preguntas con anthropic: claude-sonnet-5-5" in caplog.text


def test_the_wired_claude_asker_is_usable(wired, tmp_path, monkeypatch):
    """El doble del SDK contesta como el real y la respuesta llega a quien pregunta."""
    from types import SimpleNamespace

    from homeauto import claude

    class FakeClient:
        def __init__(self):
            self.messages = self

        def create(self, **kwargs):
            text = "RESPUESTA: Son las 15.\nVOZ: Son las quince."
            block = SimpleNamespace(type="text", text=text)
            return SimpleNamespace(content=[block], stop_reason="end_turn")

    seen = _commands_kwargs(monkeypatch)
    path = config_file(tmp_path, "LLM_API_KEY=k\nASK_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\n")
    run_main(monkeypatch, path)

    model = seen["asker"].model
    assert model.make_client is claude.anthropic_client
    model.make_client = lambda api_key, timeout: FakeClient()
    answer = seen["asker"].ask("¿Qué hora es?")
    assert answer.written == "Son las 15."
    assert answer.spoken == "Son las quince."


def test_the_startup_log_names_both_providers(wired, tmp_path, monkeypatch, caplog):
    caplog.set_level("INFO", logger="homeauto")
    path = config_file(tmp_path, "LLM_API_KEY=k\nASK_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\n")
    run_main(monkeypatch, path)

    text = caplog.text
    assert "texto con google: gemini-3.1-flash-lite" in text
    assert "preguntas con anthropic: claude-sonnet-5-5" in text
    assert "sk-x" not in text


def test_the_startup_log_names_the_provider_and_not_the_key(
    wired, tmp_path, monkeypatch, caplog
):
    caplog.set_level("INFO", logger="homeauto")
    run_main(monkeypatch, config_file(tmp_path, ANTHROPIC_ENV))

    text = caplog.text
    assert "anthropic" in text
    assert "claude-haiku-5-5" in text
    assert "sk-x" not in text


def test_a_voice_note_has_a_handler(wired, tmp_path, monkeypatch):
    run_main(monkeypatch, config_file(tmp_path, "LLM_API_KEY=una-clave\n"))

    assert len([h for h in wired.handlers if type(h).__name__ == "MessageHandler"]) >= 2


def test_the_voicemail_is_wired_and_usable(wired, tmp_path, monkeypatch):
    """El doble tiene que servir para lo que sirve el real: se lo llama."""
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen["voicemail"] = kwargs.get("voicemail")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path))

    assert callable(seen["voicemail"])


def test_the_briefing_remembers_the_night_errors(wired, tmp_path, monkeypatch):
    seen = {}
    original = main.Briefing.__init__

    def spy(self, *args, **kwargs):
        seen["seq"] = kwargs.get("seq")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Briefing, "__init__", spy)
    path = config_file(tmp_path, "SEQ_URL_VPS=http://seq\nSEQ_API_KEY_VPS=k\n")
    run_main(monkeypatch, path)

    assert seen["seq"], "el resumen no tiene con qué recordar la noche"
    assert all(hasattr(client, "errors_since") for client in seen["seq"])


# --- el cierre del día ------------------------------------------------------


def test_the_closing_is_scheduled(wired, tmp_path, monkeypatch):
    """Como el resumen, no depende de que haya un calendario configurado."""
    run_main(monkeypatch, config_file(tmp_path))

    assert "closing" in wired.job_queue.daily


def test_the_closing_can_be_turned_off(wired, tmp_path, monkeypatch):
    run_main(monkeypatch, config_file(tmp_path, "CLOSING_AT=off\n"))

    assert "closing" not in wired.job_queue.daily


def closing_built(monkeypatch):
    """Lo que main() le pasó al cierre del día."""
    seen = {}
    original = main.Closing.__init__

    def spy(self, *args, **kwargs):
        seen.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Closing, "__init__", spy)
    return seen


def test_the_closing_gets_the_weather_and_the_monitor(wired, tmp_path, monkeypatch):
    seen = closing_built(monkeypatch)
    checks = tmp_path / "checks.json"
    checks.write_text('[{"name": "vpn", "host": "10.0.0.1", "port": 443}]', encoding="utf-8")

    run_main(monkeypatch, config_file(tmp_path, f"CHECKS_FILE={checks}\n"))

    assert seen["weather"].spoken_tomorrow, "el doble tiene que poder usarse como lo real"
    assert seen["monitor"].snapshot() == {}


def test_without_a_calendar_the_closing_still_runs(wired, tmp_path, monkeypatch):
    seen = closing_built(monkeypatch)

    run_main(monkeypatch, config_file(tmp_path))

    assert seen["agenda"] is None


def test_the_closing_counts_what_is_left_to_buy(wired, tmp_path, monkeypatch):
    seen = closing_built(monkeypatch)

    run_main(monkeypatch, config_file(tmp_path))

    assert seen["lists"].items("compras") == [], "el doble tiene que poder usarse como lo real"


def test_a_key_builds_the_translator(wired, tmp_path, monkeypatch):
    got = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        got.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path, "LLM_API_KEY=una-clave\n"))

    assert got["translator"] is not None
    assert callable(got["translator"].translate)


def test_without_a_key_there_is_no_translator(wired, tmp_path, monkeypatch):
    got = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        got.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    run_main(monkeypatch, config_file(tmp_path))

    assert got["translator"] is None


def _spy_init(monkeypatch, cls):
    seen = {}
    original = cls.__init__

    def spy(self, *args, **kwargs):
        seen.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cls, "__init__", spy)
    return seen


def test_an_alarm_offers_to_be_turned_off_or_postponed(wired, tmp_path, monkeypatch):
    seen = _spy_init(monkeypatch, main.Announcer)

    run_main(monkeypatch, config_file(tmp_path))

    off, *snooze = seen["actions"]
    assert off[1].format(job=17) == "callar 17"
    assert tuple(snooze) == main.SNOOZE_ACTIONS
    [(label, data)] = seen["ring_actions"]
    assert label == "🔕 Apagar"
    assert data.format(job=17) == "callar 17"


def test_a_ringing_alarm_is_kept_in_the_one_database_and_can_be_stopped(
    wired, tmp_path, monkeypatch
):
    reminders = _spy_init(monkeypatch, main.Reminders)

    run_main(monkeypatch, config_file(tmp_path))

    ringing = reminders["ringing"]
    assert ringing.db_path == tmp_path / "jobs.db"
    ringing.remember(17, 42, "arriba", None, main.datetime(2026, 10, 15, 7, 0))
    assert ringing.take(17).message == "arriba"
    stop = reminders["stop_audio"]
    assert stop.__self__ is reminders["announce"], "corta el audio con los equipos del anunciador"
    stop([])


def test_what_fired_is_kept_in_the_one_database(wired, tmp_path, monkeypatch):
    seen = _spy_init(monkeypatch, main.Reminders)

    run_main(monkeypatch, config_file(tmp_path))

    fired = seen["fired"]
    assert fired.db_path == tmp_path / "jobs.db"
    fired.remember(42, "arriba", None, main.datetime(2026, 9, 25, 7, 30))
    assert fired.last(42).message == "arriba"


def test_a_reminder_offers_done_and_waits_in_the_one_database(wired, tmp_path, monkeypatch):
    announcer = _spy_init(monkeypatch, main.Announcer)
    reminders = _spy_init(monkeypatch, main.Reminders)

    run_main(monkeypatch, config_file(tmp_path))

    done, *snooze = announcer["reminder_actions"]
    assert done[1].format(job=17) == "hecho 17"
    assert tuple(snooze) == main.SNOOZE_ACTIONS
    awaiting = reminders["awaiting"]
    assert awaiting.db_path == tmp_path / "jobs.db"
    awaiting.remember(17, "la pastilla", main.datetime(2026, 9, 28, 8, 0))
    assert awaiting.take(17) == "la pastilla"
    assert callable(reminders["notify"])


def test_a_reminder_nags_with_only_the_done_button(wired, tmp_path, monkeypatch):
    reminders = _spy_init(monkeypatch, main.Reminders)

    run_main(monkeypatch, config_file(tmp_path))

    [(label, data)] = reminders["nag_actions"]
    assert label == "✅ Hecho"
    assert data.format(job=17) == "hecho 17"
    assert callable(reminders["notify"])


def test_what_rang_is_kept_in_the_history_of_the_one_database(wired, tmp_path, monkeypatch):
    reminders = _spy_init(monkeypatch, main.Reminders)

    run_main(monkeypatch, config_file(tmp_path))

    history = reminders["history"]
    assert history.db_path == tmp_path / "jobs.db"
    at = main.datetime(2026, 10, 5, 8, 0)
    history.record(17, 42, "reminder", "daily", "la pastilla", at)
    assert history.mark_done(17, at, "Eze")
    [entry] = history.between(at, at + timedelta(minutes=1))
    assert (entry.message, entry.closed, entry.done_by) == ("la pastilla", "done", "Eze")


def test_a_button_has_a_handler(wired, tmp_path, monkeypatch):
    run_main(monkeypatch, config_file(tmp_path))

    assert any(isinstance(h, main.CallbackQueryHandler) for h in wired.handlers)


def test_the_watchers_alert_with_their_buttons(wired, tmp_path, monkeypatch):
    monitor = _spy_init(monkeypatch, main.Monitor)
    seq = _spy_init(monkeypatch, main.SeqWatcher)
    checks = tmp_path / "checks.json"
    checks.write_text('[{"name": "vpn", "host": "10.0.0.1", "port": 443}]', encoding="utf-8")
    run_main(
        monkeypatch,
        config_file(
            tmp_path,
            f"CHECKS_FILE={checks}\nSEQ_URL=http://172.68.0.7\nSEQ_API_KEY=una-clave\n",
        ),
    )
    alerted = []
    monkeypatch.setattr(main, "_alert", lambda *args: alerted.append(args[-1]))

    monitor["announce"]("vpn no responde", True)
    seq["announce"]("errores en Seq")

    assert alerted == [main.MONITOR_ACTIONS, main.SEQ_ACTIONS]


class _FakeNotifier:
    """Anota lo que se escribiría a cada chat, como el `ChatNotifier` real."""

    sent = []

    def __init__(self, bot):
        _FakeNotifier.sent = []

    def bind(self, loop):
        pass

    def __call__(self, chat_id, text, actions=()):
        _FakeNotifier.sent.append((chat_id, text, actions))


def test_the_monitor_offers_to_confirm_reminds_and_tells_the_other_alert_chats(
    wired, tmp_path, monkeypatch
):
    monitor = _spy_init(monkeypatch, main.Monitor)
    monkeypatch.setattr(main, "ChatNotifier", _FakeNotifier)
    checks = tmp_path / "checks.json"
    checks.write_text('[{"name": "vpn", "host": "10.0.0.1", "port": 443}]', encoding="utf-8")
    run_main(
        monkeypatch,
        config_file(
            tmp_path, f"CHECKS_FILE={checks}\nALLOWED_CHAT_IDS=42,43,77\nALERT_CHAT_IDS=42,43\n"
        ),
    )
    alerted = []
    reminded = []
    monkeypatch.setattr(main, "_alert", lambda *args: alerted.append(args[-1]))
    monkeypatch.setattr(main, "_still_down", lambda *args: reminded.append(args))

    monitor["announce"]("vpn no responde", True, "timeout", check="vpn")
    monitor["remind"]("vpn sigue sin responder", "vpn", "timeout")
    monitor["tell_others"](42, "✅ Eze confirmó: vpn no responde")

    assert alerted == [main._monitor_actions("vpn")]
    [(house, text, name, detail, still)] = reminded
    assert isinstance(house, main.HouseVoice)
    assert (text, name, detail) == ("vpn sigue sin responder", "vpn", "timeout")
    assert still == "sigue sin responder"
    assert _FakeNotifier.sent == [(43, "✅ Eze confirmó: vpn no responde", ())]


def test_newcomers_are_announced_from_the_one_database(wired, tmp_path, monkeypatch):
    seen = _spy_init(monkeypatch, main.Strangers)

    run_main(monkeypatch, config_file(tmp_path, "ALLOWED_CHAT_IDS=42\n"))

    assert seen["store"].db_path == tmp_path / "jobs.db"
    assert seen["config"].allowed_chat_ids == frozenset({42})


# --- a quién le llega cada aviso ---------------------------------------------


def test_an_alarm_reaches_every_allowed_chat(wired, tmp_path, monkeypatch):
    announcer = _spy_init(monkeypatch, main.Announcer)
    reminders = _spy_init(monkeypatch, main.Reminders)

    run_main(monkeypatch, config_file(tmp_path, "ALLOWED_CHAT_IDS=42,77\n"))

    assert set(announcer["chat_ids"]) == {42, 77}
    assert set(reminders["chat_ids"]) == {42, 77}


def test_the_alerts_reach_only_the_alert_chats(wired, tmp_path, monkeypatch):
    seen = _spy_init(monkeypatch, main.HouseVoice)

    run_main(monkeypatch, config_file(tmp_path, "ALLOWED_CHAT_IDS=42,77\nALERT_CHAT_IDS=42\n"))

    assert set(seen["chat_ids"]) == {42, 77}
    assert set(seen["alert_chat_ids"]) == {42}


@pytest.mark.parametrize("schedule", ["schedule_briefing", "schedule_closing"])
def test_the_summaries_hand_over_the_copy_for_the_others(schedule, wired, tmp_path, monkeypatch):
    handed = {}
    original = getattr(main, schedule)

    def spy(app, config, source, announce):
        handed["announce"] = announce
        return original(app, config, source, announce)

    monkeypatch.setattr(main, schedule, spy)
    announced = []
    monkeypatch.setattr(main, "_announce", lambda *args: announced.append(args[1:]))

    run_main(monkeypatch, config_file(tmp_path))
    handed["announce"]("dicho", "completo", "sin servicios")

    assert announced == [("dicho", "completo", "sin servicios")]


def _wired_web(monkeypatch, tmp_path, extra=""):
    seen = _spy_init(monkeypatch, main.ApiServer)
    run_main(
        monkeypatch, config_file(tmp_path, "API_TOKEN=un-token-suficientemente-largo\n" + extra)
    )
    return seen["web"]


def test_the_api_serves_a_usable_screen(wired, tmp_path, monkeypatch):
    """La pantalla llega al servidor de la API y se puede pedir de verdad."""
    web = _wired_web(monkeypatch, tmp_path)

    for path in ("/agenda", "/pantalla", "/static/app.js"):
        assert web.handle(Request(method="GET", path=path)).status == 200, path
    response = web.handle(
        Request(method="GET", path="/api/events", query={"start": "2026-10-01", "end": "2026-11-01"})
    )
    assert response.status == 200
    assert json.loads(response.body)["problems"] == []


def test_the_screen_reads_the_one_database(wired, tmp_path, monkeypatch):
    web = _wired_web(monkeypatch, tmp_path)
    board = web.board
    board.store.add(42, main.datetime(2099, 1, 2, 8, 0), "arriba")
    board.lists.add("compras", ["leche"])
    board.weather.fetch = lambda latitude, longitude: {}

    events = board.events(main.datetime(2099, 1, 1), main.datetime(2099, 1, 8))
    screen = board.screen()

    assert board.store.db_path == tmp_path / "jobs.db"
    assert [event["title"] for event in events["events"]] == ["⏰ arriba"]
    assert [item["text"] for item in screen["lists"]["compras"]] == ["leche"]
    assert screen["weather"] is None
    assert isinstance(screen["quiet"], bool)
    assert board.quiet.until() is None


def test_the_screen_serves_the_tv_app_from_the_state_directory(wired, tmp_path, monkeypatch):
    """El estante apunta a STATE_DIR / "app" y el APK que se deja ahí se baja."""
    web = _wired_web(monkeypatch, tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "tele.apk").write_bytes(b"PK\x03\x04apk")

    assert web.apps.directory == tmp_path / "app"
    assert web.apps.get("tele.apk") == b"PK\x03\x04apk"
    response = web.handle(Request(method="GET", path="/app/tele.apk"))
    assert response.status == 200
    assert response.body == b"PK\x03\x04apk"


def test_the_screen_shows_the_meal_idea_from_the_one_database(wired, tmp_path, monkeypatch):
    web = _wired_web(monkeypatch, tmp_path, "MENU_LUNCH_AT=off\n")
    board = web.board
    today = main.datetime.now().date()
    board.meals.replace(Meal(today, LUNCH, "Milanesas", ("carne",)))
    board.meals.replace(Meal(today + timedelta(days=1), LUNCH, "Ñoquis", ("papas",)))
    board.meals.replace(Meal(today, DINNER, "Tarta", ("acelga",)))
    board.meals.replace(Meal(today + timedelta(days=1), DINNER, "Pizza", ("harina",)))

    meal = board.screen()["meal"]

    assert board.meals.db_path == tmp_path / "jobs.db"
    assert board.served == ("cena",)
    assert [item["meal"] for item in meal["items"]] == ["cena"]


def test_the_screen_shows_the_configured_calendars(wired, tmp_path, monkeypatch):
    web = _wired_web(monkeypatch, tmp_path, "CALENDAR_URL_PERSONAL=https://ejemplo/a.ics\n")

    assert web.board.aliases == ["personal"]
    assert web.board.calendar.timezone == main.local_timezone()


HOUSE = "ALLOWED_CHAT_IDS=42,77\n"
WRITE = {"Content-Type": "application/json", "Host": "casa:8080", "Origin": "http://casa:8080"}


def test_the_screen_writes_to_the_one_database_and_tells_every_chat(wired, tmp_path, monkeypatch):
    reminders = _spy_init(monkeypatch, main.Reminders)
    web = _wired_web(monkeypatch, tmp_path, HOUSE)
    jobs = web.jobs
    pending = []
    jobs.spawn = pending.append

    body = json.dumps({"type": "alarm", "message": "arriba", "when": "2099-01-02T08:00",
                       "repeat": "once", "days": [], "device": "parlante", "author": 77})
    response = web.handle(Request.from_target("POST", "/api/jobs", headers=WRITE,
                                              body=body.encode("utf-8")))

    assert response.status == 201
    created = json.loads(response.body)
    job = jobs.store.get(created["id"])
    assert jobs.store.db_path == tmp_path / "jobs.db"
    assert (job.chat_id, job.message, job.device) == (77, "arriba", "parlante")
    assert web.board.store.get(created["id"]) == job
    assert isinstance(jobs.notify, main.ChatNotifier)
    assert jobs.notify is reminders["notify"]
    assert sorted(jobs.chat_ids) == [42, 77]
    assert len(pending) == 1


def test_the_screen_knows_the_people_of_the_house(wired, tmp_path, monkeypatch):
    registered = {}
    original = main.register

    def spy(app, commands, strangers=None, people=None):
        registered["people"] = people
        return original(app, commands, strangers, people)

    monkeypatch.setattr(main, "register", spy)
    web = _wired_web(monkeypatch, tmp_path, HOUSE)

    registered["people"].meet(42, "Eze")
    registered["people"].meet(99, "Un desconocido")
    answer = json.loads(web.handle(Request(method="GET", path="/api/people")).body)

    assert answer == {"writable": True, "people": [
        {"chat_id": 42, "name": "Eze"}, {"chat_id": 77, "name": "Chat 77"},
    ], "devices": ["parlante"]}


def test_the_screen_crosses_out_from_the_one_database(wired, tmp_path, monkeypatch):
    web = _wired_web(monkeypatch, tmp_path, HOUSE)
    web.board.lists.add("compras", ["leche"])
    [(item_id, _)] = web.board.lists.entries("compras")

    response = web.handle(Request.from_target(
        "POST", f"/api/lists/compras/{item_id}/done", headers=WRITE, body=b"{}"))

    assert response.status == 200
    assert web.board.lists.items("compras") == []


def test_without_allowed_chats_the_screen_does_not_write(wired, tmp_path, monkeypatch):
    web = _wired_web(monkeypatch, tmp_path)

    response = web.handle(Request.from_target("POST", "/api/jobs", headers=WRITE, body=b"{}"))

    assert response.status == 403


def test_the_tele_app_registers_and_polls_on_the_one_database(wired, tmp_path, monkeypatch):
    """Con API, la tele se registra y su consulta trae la alarma que guardó la pantalla."""
    web = _wired_web(monkeypatch, tmp_path, HOUSE + "SCREEN_DEVICES=comedor,recamara\n")
    tele = web.tele

    assert tele.link.store.db_path == tmp_path / "jobs.db"
    assert tele.screens.db_path == tmp_path / "jobs.db"
    setup = json.loads(web.handle(Request(method="GET", path="/api/tele/setup")).body)
    assert setup["devices"] == ["comedor", "recamara"]
    assert [person["chat_id"] for person in setup["people"]] == [42, 77]

    hello = web.handle(Request.from_target(
        "POST", "/api/tele/hello", headers=WRITE, client="192.168.68.20",
        body=json.dumps({"alias": "comedor", "version_name": "1.0", "version_code": 1,
                         "caps": ["play", "show"]}).encode("utf-8")))
    assert hello.status == 200
    tele.screens.show("comedor", 17)

    poll = web.handle(Request(method="GET", path="/api/tele/comedor/poll"))
    assert poll.status == 200
    assert json.loads(poll.body) == {"alarm": 17, "orders": []}
    assert main.TeleStore(tmp_path / "jobs.db").get("comedor").address == "192.168.68.20"
    assert tele.link.alive("comedor")


def test_without_a_token_there_is_no_tele_app(wired, tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(main.TeleStore, "__init__", lambda self, *a, **k: built.append(a))
    monkeypatch.setattr(main.TeleService, "__init__", lambda self, *a, **k: built.append(k))

    run_main(monkeypatch, config_file(tmp_path))

    assert built == []


def test_without_a_token_there_is_no_screen(wired, tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(main.ApiServer, "__init__", lambda self, *a, **k: built.append(k))

    run_main(monkeypatch, config_file(tmp_path))

    assert built == []


# --- el resumen semanal ------------------------------------------------------


def test_the_weekly_summary_goes_out_on_sunday_by_default(wired, tmp_path, monkeypatch):
    """PTB cuenta el domingo como cero."""
    run_main(monkeypatch, config_file(tmp_path))

    assert wired.job_queue.days["weekly"] == (0,)


def test_the_weekly_summary_days_are_translated_for_the_job_queue(wired, tmp_path, monkeypatch):
    run_main(monkeypatch, config_file(tmp_path, "WEEKLY_AT=lun,sáb,dom 9:00\n"))

    assert sorted(wired.job_queue.days["weekly"]) == [0, 1, 6]


def test_the_weekly_summary_can_be_turned_off(wired, tmp_path, monkeypatch):
    run_main(monkeypatch, config_file(tmp_path, "WEEKLY_AT=off\n"))

    assert "weekly" not in wired.job_queue.daily


def test_the_weekly_summary_reads_the_history_and_writes_to_everyone(
    wired, tmp_path, monkeypatch
):
    seen = _spy_init(monkeypatch, main.Weekly)
    monkeypatch.setattr(main, "ChatNotifier", _FakeNotifier)
    run_main(monkeypatch, config_file(tmp_path, "ALLOWED_CHAT_IDS=42,77\n"))
    history = seen["history"]
    assert history.db_path == tmp_path / "jobs.db"
    fired = main.datetime.now() - timedelta(days=1)
    history.record(5, 42, "reminder", "daily", "la pastilla", fired)
    history.mark_done(5, fired, "Eze")

    main.asyncio.run(wired.job_queue.callbacks["weekly"](None))

    assert [chat for chat, _, _ in _FakeNotifier.sent] == [42, 77]
    assert all("la pastilla: 1 de 1" in text for _, text, _ in _FakeNotifier.sent)


def test_an_empty_week_writes_nothing(wired, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ChatNotifier", _FakeNotifier)
    run_main(monkeypatch, config_file(tmp_path, "ALLOWED_CHAT_IDS=42,77\n"))

    main.asyncio.run(wired.job_queue.callbacks["weekly"](None))

    assert _FakeNotifier.sent == []


# --- internet ------------------------------------------------------------------


def _spy_uplinks(monkeypatch):
    """Registra cada Uplink que arma main() y le cambia la red por un doble."""
    built = []
    original = main.Uplink.__init__

    def spy(self, *args, **kwargs):
        kwargs["connect"] = lambda host, port, timeout: 0.01
        original(self, *args, **kwargs)
        built.append(self)

    monkeypatch.setattr(main.Uplink, "__init__", spy)
    return built


async def test_the_uplink_is_watched_even_without_checks(wired, tmp_path, monkeypatch):
    built = _spy_uplinks(monkeypatch)

    run_main(monkeypatch, config_file(tmp_path))

    assert len(built) == 1
    assert "service-watch" in wired.job_queue.repeating
    await wired.job_queue.callbacks["service-watch"](None)
    assert built[0].online is True


async def test_the_uplink_runs_before_the_monitor(wired, tmp_path, monkeypatch):
    order = []
    monkeypatch.setattr(main.Uplink, "run_once", lambda self: order.append("uplink") or True)
    monkeypatch.setattr(main.Monitor, "run_once", lambda self: order.append("monitor") or [])
    checks = tmp_path / "checks.json"
    checks.write_text('[{"name": "vpn", "host": "10.0.0.1", "port": 443}]', encoding="utf-8")

    run_main(monkeypatch, config_file(tmp_path, f"CHECKS_FILE={checks}\n"))
    await wired.job_queue.callbacks["service-watch"](None)

    assert order == ["uplink", "monitor"]


def test_the_monitor_and_seq_ask_the_uplink(wired, tmp_path, monkeypatch):
    uplinks = _spy_uplinks(monkeypatch)
    monitors, seqs = [], []
    for cls, sink in ((main.Monitor, monitors), (main.SeqWatcher, seqs)):
        original = cls.__init__

        def spy(self, *args, __original=original, __sink=sink, **kwargs):
            __original(self, *args, **kwargs)
            __sink.append(self)

        monkeypatch.setattr(cls, "__init__", spy)
    checks = tmp_path / "checks.json"
    checks.write_text('[{"name": "vpn", "host": "10.0.0.1", "port": 443}]', encoding="utf-8")
    path = config_file(
        tmp_path,
        f"CHECKS_FILE={checks}\nSEQ_URL=http://172.68.0.7\nSEQ_API_KEY=una-clave\n",
    )

    run_main(monkeypatch, path)
    uplinks[0].online = False

    assert monitors[0].online() is False
    assert seqs[0].online() is False


def test_the_wired_uplink_speaks_softly_and_tells_everyone(wired, tmp_path, monkeypatch):
    from homeauto.voice import chime

    uplinks = _spy_uplinks(monkeypatch)
    spoken, told = [], []
    monkeypatch.setattr(
        main.HouseVoice, "speak_only", lambda self, text, chime=False: spoken.append((text, chime))
    )
    monkeypatch.setattr(main.HouseVoice, "tell_everyone", lambda self, text, actions=(): told.append(text))

    run_main(monkeypatch, config_file(tmp_path))
    uplinks[0].speak("Se cortó internet.")
    uplinks[0].tell("🌐 Internet se cortó")

    assert spoken == [("Se cortó internet.", chime.SOFT)]
    assert told == ["🌐 Internet se cortó"]


# --- feriados ---------------------------------------------------------------

HOLIDAYS_2026 = [
    {"fecha": "2026-10-12", "tipo": "trasladable", "nombre": "Día del Respeto a la Diversidad Cultural"},
]


def _fake_holiday_api(monkeypatch):
    """El cliente real de feriados con un fetch que no sale a la red."""
    from homeauto.holidays import HolidayClient

    asked = []

    def fetch(url):
        asked.append(url)
        return HOLIDAYS_2026 if url.endswith("/2026") else []

    monkeypatch.setattr(main, "HolidayClient", lambda: HolidayClient(fetch=fetch))
    return asked


def test_the_holidays_are_refreshed_at_startup_and_every_night(wired, tmp_path, monkeypatch):
    run_main(monkeypatch, config_file(tmp_path))

    assert "holidays" in wired.job_queue.daily
    assert "holidays-startup" in wired.job_queue.once


def test_the_holiday_refresh_fills_the_one_database_the_alarms_read(wired, tmp_path, monkeypatch):
    asked = _fake_holiday_api(monkeypatch)
    reminders = _spy_init(monkeypatch, main.Reminders)
    monkeypatch.setattr(main, "date", type("FixedDate", (main.date,), {
        "today": classmethod(lambda cls: main.date(2026, 10, 15)),
    }))

    run_main(monkeypatch, config_file(tmp_path))
    holiday_of = reminders["holidays"]
    assert holiday_of(main.date(2026, 10, 12)) is None, "antes de refrescar no hay nada"

    main.asyncio.run(wired.job_queue.callbacks["holidays-startup"](None))

    assert asked == ["https://api.argentinadatos.com/v1/feriados/2026"]
    assert holiday_of(main.date(2026, 10, 12)).name == "Día del Respeto a la Diversidad Cultural"
    assert holiday_of(main.date(2026, 10, 13)) is None


def test_the_nightly_refresh_runs_too(wired, tmp_path, monkeypatch):
    asked = _fake_holiday_api(monkeypatch)

    run_main(monkeypatch, config_file(tmp_path))
    main.asyncio.run(wired.job_queue.callbacks["holidays"](None))

    assert asked, "el refresco diario tiene que pedir los feriados"


def test_the_briefing_reads_the_holidays(wired, tmp_path, monkeypatch):
    seen = briefing_built(monkeypatch)

    run_main(monkeypatch, config_file(tmp_path, "BRIEFING_AT=08:00\n"))

    assert seen["holidays"](main.date(2026, 10, 12)) is None
    assert seen["holidays"].__self__.db_path == tmp_path / "jobs.db"


def test_the_screen_shows_the_holidays_of_the_one_database(wired, tmp_path, monkeypatch):
    from homeauto.holidays import MOVABLE, Holiday

    web = _wired_web(monkeypatch, tmp_path)
    board = web.board
    board.holidays.replace(2026, [Holiday(main.date(2026, 10, 12), MOVABLE, "Diversidad")])

    events = board.events(main.datetime(2026, 10, 12), main.datetime(2026, 10, 13))["events"]

    assert board.holidays.db_path == tmp_path / "jobs.db"
    assert [event["title"] for event in events] == ["🏖 Diversidad"]


def test_the_pills_are_counted_in_the_one_database(wired, tmp_path, monkeypatch):
    reminders = _spy_init(monkeypatch, main.Reminders)
    commands = _spy_init(monkeypatch, main.Commands)

    run_main(monkeypatch, config_file(tmp_path))

    stock = reminders["stock"]
    assert stock is commands["stock"], "el comando y el «Hecho» cuentan el mismo stock"
    assert stock.db_path == tmp_path / "jobs.db"
    supply, _ = stock.ensure("enalapril", 8)
    assert stock.take_dose(supply.id) == (stock.get(supply.id), True)
    lists = reminders["lists"]
    assert lists.db_path == tmp_path / "jobs.db"
    assert lists.add("compras", ["enalapril"]) == ["enalapril"]


# --- modo vacaciones ---------------------------------------------------------


def test_the_vacations_live_in_the_one_database_and_quiet_everything(wired, tmp_path, monkeypatch):
    hush = _spy_init(monkeypatch, main.Hush)
    reminders = _spy_init(monkeypatch, main.Reminders)
    house = _spy_init(monkeypatch, main.HouseVoice)

    run_main(monkeypatch, config_file(tmp_path))

    away = hush["away"]
    assert isinstance(away, main.AwayStore)
    assert away.db_path == tmp_path / "jobs.db"
    away.set(main.datetime(2099, 1, 1))
    assert away.until() == main.datetime(2099, 1, 1)
    assert reminders["quiet"] is house["quiet"], "las alarmas y la casa leen el mismo silencio"
    assert reminders["quiet"].is_away() is True


def test_the_vacations_command_arms_the_end_on_the_job_queue(wired, tmp_path, monkeypatch):
    commands = _spy_init(monkeypatch, main.Commands)
    monkeypatch.setattr(main, "ChatNotifier", _FakeNotifier)

    run_main(monkeypatch, config_file(tmp_path, "ALLOWED_CHAT_IDS=42,77\n"))
    vacation = commands["vacation"]
    vacation.begin(main.datetime(2099, 1, 1), 42, "Eze")

    from homeauto.quiet import AWAY_END_KEY

    assert AWAY_END_KEY in wired.job_queue.once
    assert commands["quiet"].is_away() is True
    assert _FakeNotifier.sent == [(77, "🧳 Eze activó vacaciones hasta el 01/01", ())]
    assert vacation.end(42, "Eze") is True


def test_the_post_init_rearms_the_end_of_the_vacations(wired, tmp_path, monkeypatch):
    handed = {}
    original = main.build_post_init

    def spy(notifier, reminders, api=None, vacation=None):
        handed["vacation"] = vacation
        return original(notifier, reminders, api, vacation)

    monkeypatch.setattr(main, "build_post_init", spy)
    commands = _spy_init(monkeypatch, main.Commands)

    run_main(monkeypatch, config_file(tmp_path))

    assert handed["vacation"] is commands["vacation"]
    assert callable(handed["vacation"].start)


def test_the_vacations_stop_the_alarms_of_the_wired_reminders(wired, tmp_path, monkeypatch):
    vacation = _spy_init(monkeypatch, main.Vacation)
    reminders = _spy_init(monkeypatch, main.Reminders)

    run_main(monkeypatch, config_file(tmp_path))

    stop = vacation["stop_ringing"]
    assert stop.__self__.ringing is reminders["ringing"]
    reminders["ringing"].remember(17, 42, "arriba", None, main.datetime(2026, 10, 15, 7, 0))
    assert stop() == 1
    assert reminders["ringing"].get(17) is None


# Inventado: la forma de un token de la API de Proxmox, no uno real.
PVE_TOKEN = "monitor@pve!casa=0b6f3a52-1c7e-4d2a-9e8b-5f4c3d2a1b0e"


def pve_config(tmp_path, checks="[]"):
    ca = tmp_path / "pve-ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    checks_file = tmp_path / "checks.json"
    checks_file.write_text(checks, encoding="utf-8")
    return config_file(
        tmp_path,
        f"CHECKS_FILE={checks_file}\nPVE_URL=https://192.0.2.10:8006\n"
        f"PVE_TOKEN={PVE_TOKEN}\nPVE_CA_FILE={ca}\nPVE_DISK_ALERT=90\n",
    )


async def test_the_proxmox_is_watched_even_with_an_empty_checks_file(wired, tmp_path, monkeypatch):
    monitor = _spy_init(monkeypatch, main.Monitor)
    commands = _spy_init(monkeypatch, main.Commands)
    said = []
    monkeypatch.setattr(main, "_alert", lambda house, text, urgent, detail, actions: said.append(text))

    run_main(monkeypatch, pve_config(tmp_path))

    names = [check.name for check in monitor["checks"]]
    assert names == ["proxmox", "el disco del proxmox", "las máquinas del proxmox", "los respaldos"]
    assert commands["monitor"] is not None
    assert monitor["store"].db_path == tmp_path / "jobs.db"

    client = monitor["checks"][0].probe.client
    assert client.url == "https://192.0.2.10:8006"
    assert client.verify == str(tmp_path / "pve-ca.pem")
    assert monitor["checks"][1].probe.alert == 90

    calls = []

    def fetch(url, headers, verify, timeout):
        calls.append(url)
        return 401, None

    client.fetch = fetch
    monkeypatch.setattr(main.Uplink, "run_once", lambda self: True)
    await wired.job_queue.callbacks["service-watch"](None)
    await wired.job_queue.callbacks["service-watch"](None)

    assert calls, "la ronda del monitor consulta el Proxmox"
    assert said and "proxmox" in said[0]


def test_the_proxmox_adds_to_the_checks_of_the_file(wired, tmp_path, monkeypatch):
    monitor = _spy_init(monkeypatch, main.Monitor)

    run_main(monkeypatch, pve_config(tmp_path, '[{"name": "vpn", "host": "10.0.0.1", "port": 443}]'))

    assert [check.name for check in monitor["checks"]][:2] == ["vpn", "proxmox"]


def test_the_stopped_machines_are_reminded_with_their_wording(wired, tmp_path, monkeypatch):
    monitor = _spy_init(monkeypatch, main.Monitor)
    reminded = []
    monkeypatch.setattr(main, "_still_down", lambda *args: reminded.append(args))

    run_main(monkeypatch, pve_config(tmp_path))
    monitor["remind"]("x", "las máquinas del proxmox", "paradas: 301 (recetas)")

    assert reminded[0][2:] == (
        "las máquinas del proxmox", "paradas: 301 (recetas)", "siguen sin estar todas en marcha"
    )


def test_without_proxmox_an_empty_checks_file_has_no_monitor(wired, tmp_path, monkeypatch):
    commands = _spy_init(monkeypatch, main.Commands)

    run_main(monkeypatch, config_file(tmp_path))

    assert commands["monitor"] is None


# --- la pantalla en la tele ---------------------------------------------------


TOKEN = "API_TOKEN=un-token-suficientemente-largo\n"


def test_without_a_token_there_are_no_screens(wired, tmp_path, monkeypatch):
    commands = _spy_init(monkeypatch, main.Commands)
    reminders = _spy_init(monkeypatch, main.Reminders)

    run_main(monkeypatch, config_file(tmp_path))

    assert commands["screens"] is None
    assert reminders["screen"] is None
    assert commands["config"].screen_device == "comedor"


def test_the_screens_are_wired_to_the_one_database_and_usable(wired, tmp_path, monkeypatch):
    commands = _spy_init(monkeypatch, main.Commands)
    reminders = _spy_init(monkeypatch, main.Reminders)
    handed = {}

    def build_speakers(config, synth=None, restore=None, tele=None):
        handed["restore"] = restore
        return _FakeRegistry()

    monkeypatch.setattr(main, "build_speakers", build_speakers)
    monkeypatch.setattr(main, "local_ip", lambda: "192.0.2.10")

    run_main(monkeypatch, config_file(tmp_path, TOKEN + "SCREEN_DEVICES=comedor,recamara\n"))

    screens = commands["screens"]
    assert screens is reminders["screen"]
    assert screens.pages.store.db_path == tmp_path / "jobs.db"
    assert screens.pages.quiet is reminders["quiet"]
    assert isinstance(screens.timer, main.JobQueueTimer)
    assert screens.is_screen("recamara") and not screens.is_screen("parlante")
    assert screens.fallback == "parlante"
    from homeauto.quiet import QuietHours

    screens.pages.quiet.hours = QuietHours.parse("00:00", "00:00")
    assert screens.restore_url("comedor") == "http://192.0.2.10:8099/pantalla?ver=1"
    assert handed["restore"]("comedor") == "http://192.0.2.10:8099/pantalla?ver=1"
    screens.pages.store.show("recamara", 17)
    assert handed["restore"]("recamara") == "http://192.0.2.10:8099/alarma?job=17"


def test_the_alarm_view_is_served_from_the_one_database(wired, tmp_path, monkeypatch):
    reminders = _spy_init(monkeypatch, main.Reminders)
    web = _wired_web(monkeypatch, tmp_path)

    assert web.handle(Request(method="GET", path="/alarma")).status == 200
    reminders["ringing"].remember(17, 42, "arriba", None, main.datetime(2026, 10, 15, 7, 0))
    answer = json.loads(web.handle(Request(method="GET", path="/api/ringing/17")).body)
    assert (answer["ringing"], answer["message"]) == (True, "arriba")
    assert json.loads(web.handle(Request(method="GET", path="/api/ringing/18")).body)["ringing"] is False


def test_each_caster_brings_back_the_page_of_its_own_tv(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "local_ip", lambda: "192.0.2.10")
    monkeypatch.setattr(main, "CACHE_DIR", str(tmp_path / "cache"))
    path = config_file(tmp_path).parent / "otro.env"
    path.write_text(
        "TELEGRAM_TOKEN=123:ABC\n"
        f"CAST_DEVICES=comedor:{uuid.uuid4()},recamara:{uuid.uuid4()}\n",
        encoding="utf-8",
    )
    config = main.Config.from_file(path)

    registry = main.build_speakers(config, synth=object(), restore=lambda alias: f"pagina de {alias}")

    assert registry.get("comedor").caster.screen() == "pagina de comedor"
    assert registry.get("recamara").caster.screen() == "pagina de recamara"
    assert main.build_speakers(config, synth=object()).get("comedor").caster.screen is None


# --- la app de la tele en los parlantes ---


def test_only_the_screens_go_through_the_tele_app(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "local_ip", lambda: "192.0.2.10")
    monkeypatch.setattr(main, "CACHE_DIR", str(tmp_path / "cache"))
    path = tmp_path / "teles.env"
    path.write_text(
        "TELEGRAM_TOKEN=123:ABC\n"
        f"CAST_DEVICES=comedor:{uuid.uuid4()},parlante:{uuid.uuid4()}\n"
        "SCREEN_DEVICES=comedor\n",
        encoding="utf-8",
    )
    config = main.Config.from_file(path)
    link = main.TeleLink(main.TeleStore(tmp_path / "jobs.db"))
    link.hello("comedor", "1.0", 1, ["play"], "")

    registry = main.build_speakers(
        config, synth=object(), restore=lambda alias: f"pagina de {alias}", tele=link
    )

    comedor = registry.get("comedor").caster
    assert isinstance(comedor, main.TeleCaster)
    assert comedor.link is link and comedor.alias == "comedor"
    assert isinstance(comedor.caster, main.Caster)
    assert comedor.screen() == "pagina de comedor", "el Caster de adentro sigue restaurando"
    seq = link.send("comedor", "stop")
    assert comedor.link.orders("comedor") == [{"seq": seq, "kind": "stop"}]
    assert type(registry.get("parlante").caster) is main.Caster
    plain = main.build_speakers(config, synth=object())
    assert type(plain.get("comedor").caster) is main.Caster


def test_the_speakers_and_the_tele_app_share_one_link(wired, tmp_path, monkeypatch):
    handed = {}

    def build_speakers(config, synth=None, restore=None, tele=None):
        handed["tele"] = tele
        return _FakeRegistry()

    monkeypatch.setattr(main, "build_speakers", build_speakers)

    web = _wired_web(monkeypatch, tmp_path, HOUSE + "SCREEN_DEVICES=comedor\n")

    link = handed["tele"]
    assert link is web.tele.link
    assert link.store.db_path == tmp_path / "jobs.db"
    web.handle(Request.from_target(
        "POST", "/api/tele/hello", headers=WRITE,
        body=json.dumps({"alias": "comedor", "version_name": "1.0", "version_code": 1,
                         "caps": ["play"]}).encode("utf-8")))
    seq = link.send("comedor", "play", url="u", min_volume=None, seconds=None)
    poll = json.loads(web.handle(Request(method="GET", path="/api/tele/comedor/poll")).body)
    assert [order["seq"] for order in poll["orders"]] == [seq]
    ack = web.handle(Request.from_target(
        "POST", "/api/tele/comedor/ack", headers=WRITE,
        body=json.dumps({"seq": seq, "state": "received"}).encode("utf-8")))
    assert json.loads(ack.body) == {"accepted": True}
    assert link.wait("comedor", seq, ("received",), timeout=0) == "received"


def test_without_a_token_the_speakers_do_not_go_through_the_tele_app(
    wired, tmp_path, monkeypatch
):
    handed = {}

    def build_speakers(config, synth=None, restore=None, tele=None):
        handed["tele"] = tele
        return _FakeRegistry()

    monkeypatch.setattr(main, "build_speakers", build_speakers)

    run_main(monkeypatch, config_file(tmp_path))

    assert handed == {"tele": None}


# --- la pantalla de control ---


def test_the_control_runs_real_commands_on_the_one_database(wired, tmp_path, monkeypatch):
    registered = {}
    original = main.register

    def spy(app, commands, strangers=None, people=None):
        registered["commands"] = commands
        registered["people"] = people
        return original(app, commands, strangers, people)

    monkeypatch.setattr(main, "register", spy)
    web = _wired_web(monkeypatch, tmp_path, HOUSE)
    control = web.control
    registered["people"].meet(42, "Eze")

    assert control.commands is registered["commands"]
    assert sorted(control.chat_ids) == [42, 77]
    assert sorted(control.alert_recipients) == [42, 77]
    assert control.quiet is web.board.quiet
    assert control.ringing.db_path == tmp_path / "jobs.db"
    assert control.monitor is None

    response = web.handle(Request.from_target(
        "POST", "/api/command", headers=WRITE,
        body=json.dumps({"chat_id": 42, "data": "lista"}).encode("utf-8")))

    assert response.status == 200
    assert json.loads(response.body) == {"text": "No hay nada programado", "actions": []}
    assert control.people.names() == {42: "Eze"}


def test_the_control_reads_what_rang_from_the_stores_reminders_writes(wired, tmp_path, monkeypatch):
    reminders = _spy_init(monkeypatch, main.Reminders)
    web = _wired_web(monkeypatch, tmp_path, HOUSE)
    control = web.control
    now = datetime.now()
    reminders["ringing"].remember(17, 42, "arriba", None, now)
    reminders["awaiting"].remember(9, "pastilla", now)
    reminders["fired"].remember(42, "pastilla", None, now, job_id=9)

    response = web.handle(Request(method="GET", path="/api/live", query={"chat": "42"}))

    assert response.status == 200
    live = json.loads(response.body)
    assert [ring["job_id"] for ring in live["ringing"]] == [17]
    assert [wait["job_id"] for wait in live["awaiting"]] == [9]
    assert live["snooze"]["job_id"] == 9
    assert control.awaiting.db_path == reminders["awaiting"].db_path


def test_the_control_sees_the_monitor_of_the_house(wired, tmp_path, monkeypatch):
    monitor = _spy_init(monkeypatch, main.Monitor)
    checks = tmp_path / "checks.json"
    checks.write_text('[{"name": "vpn", "host": "10.0.0.1", "port": 443}]', encoding="utf-8")
    web = _wired_web(monkeypatch, tmp_path, HOUSE + f"CHECKS_FILE={checks}\n")

    assert web.control.monitor is not None
    assert web.control.monitor.store is monitor["store"]
    assert web.control.live(42)["status"] == []


def test_without_allowed_chats_the_control_does_not_run_commands(wired, tmp_path, monkeypatch):
    web = _wired_web(monkeypatch, tmp_path)

    response = web.handle(Request.from_target(
        "POST", "/api/command", headers=WRITE,
        body=json.dumps({"chat_id": 42, "data": "lista"}).encode("utf-8")))

    assert response.status == 403


# --- menú de la semana ---


def _week_reply(prompt):
    """Contesta como el modelo: una semana válida, o un plato si se pide uno."""
    if '"dias"' not in prompt:
        return json.dumps({"plato": "Tarta de acelga", "ingredientes": ["acelga", "huevos"]})
    days = [
        {meal: {"plato": f"Plato {meal} {i}", "ingredientes": ["papas", "sal"]}
         for meal in ("almuerzo", "cena")}
        for i in range(7)
    ]
    return "```json\n" + json.dumps({"dias": days}) + "\n```"


def _wired_commands(monkeypatch):
    """Los kwargs y el `Commands` que arma `main()`."""
    seen = {}
    original = main.Commands.__init__

    def spy(self, *args, **kwargs):
        seen.update(kwargs, commands=self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(main.Commands, "__init__", spy)
    return seen


def test_without_a_key_the_menu_has_its_table_but_no_planner(wired, tmp_path, monkeypatch):
    seen = _wired_commands(monkeypatch)
    run_main(monkeypatch, config_file(tmp_path, HOUSE))

    assert seen["meal_planner"] is None
    assert seen["meal_store"].db_path == tmp_path / "jobs.db"
    assert "LLM_API_KEY" in seen["commands"].menu(42, "")


def test_the_menu_planner_uses_the_cheap_model_with_its_own_timeout(wired, tmp_path, monkeypatch):
    seen = _wired_commands(monkeypatch)
    run_main(monkeypatch, config_file(tmp_path, HOUSE + "LLM_API_KEY=k\nLLM_MODEL=barato\n"))

    model = seen["meal_planner"].model
    assert isinstance(model, polish.GoogleModel)
    assert model.model == "barato"
    assert model.search is False
    assert model.timeout == main.MENU_TIMEOUT


def test_the_wired_menu_is_made_saved_and_changed_on_the_one_database(wired, tmp_path, monkeypatch):
    """🔴 El doble contesta JSON como el modelo y el menú llega a la tabla de verdad."""
    import sqlite3

    monkeypatch.setattr(main, "ChatNotifier", _FakeNotifier)
    seen = _wired_commands(monkeypatch)
    run_main(monkeypatch, config_file(tmp_path, HOUSE + "LLM_API_KEY=k\n"))
    seen["meal_planner"].model = _week_reply
    commands = seen["commands"]
    commands.clock = lambda: datetime(2026, 10, 20, 10, 0)

    week = commands.menu(42, "")

    assert "Plato almuerzo 0" in week
    with sqlite3.connect(tmp_path / "jobs.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM meal_plans").fetchone()[0] == 14

    commands.press(42, "menu otra 2026-10-21 cena", who="Eze")

    assert seen["meal_store"].get(datetime(2026, 10, 21).date(), "cena").dish == "Tarta de acelga"
    assert [(chat, text.split(":")[0]) for chat, text, _ in _FakeNotifier.sent] == [
        (77, "🍽 Eze cambió la cena del miércoles 21/10")
    ]


# --- el aviso antes de cada comida ---


def test_each_meal_reminder_is_scheduled_at_its_configured_hour(wired, tmp_path, monkeypatch):
    run_main(
        monkeypatch,
        config_file(tmp_path, "LLM_API_KEY=k\nMENU_LUNCH_AT=11:15\nMENU_DINNER_AT=18:00\n"),
    )

    lunch, dinner = wired.job_queue.times["menu-lunch"], wired.job_queue.times["menu-dinner"]
    assert (lunch.hour, lunch.minute) == (11, 15)
    assert (dinner.hour, dinner.minute) == (18, 0)
    assert lunch.tzinfo is not None and dinner.tzinfo is not None


def test_a_meal_turned_off_has_no_reminder(wired, tmp_path, monkeypatch):
    run_main(monkeypatch, config_file(tmp_path, "LLM_API_KEY=k\nMENU_LUNCH_AT=off\n"))

    assert "menu-lunch" not in wired.job_queue.daily
    assert "menu-dinner" in wired.job_queue.daily


def test_without_a_key_no_meal_reminder_is_scheduled(wired, tmp_path, monkeypatch):
    run_main(monkeypatch, config_file(tmp_path))

    assert "menu-lunch" not in wired.job_queue.daily
    assert "menu-dinner" not in wired.job_queue.daily


async def test_the_meal_reminder_runs_off_the_loop_and_writes_to_everyone_with_buttons(
    wired, tmp_path, monkeypatch
):
    """🔴 El aviso sale del menú guardado y sus botones andan con `/menu`."""
    from homeauto.meals import Meal, week_of

    monkeypatch.setattr(main, "ChatNotifier", _FakeNotifier)
    seen = _wired_commands(monkeypatch)
    threaded = []
    real_to_thread = main.asyncio.to_thread

    async def to_thread(func, *args, **kwargs):
        threaded.append(func)
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(main.asyncio, "to_thread", to_thread)
    run_main(monkeypatch, config_file(tmp_path, HOUSE + "LLM_API_KEY=k\n"))
    seen["meal_planner"].model = _week_reply
    today = main.datetime.now().date()
    seen["meal_store"].save_week(
        week_of(today), [Meal(today, "cena", "Tarta de choclo", ("choclo", "huevos"))]
    )

    await wired.job_queue.callbacks["menu-dinner"](None)

    assert threaded
    assert [chat for chat, _, _ in _FakeNotifier.sent] == [42, 77]
    _chat, text, actions = _FakeNotifier.sent[0]
    assert text == "🍽 Idea para la cena: Tarta de choclo.\nLleva: choclo, huevos."
    assert [data for _label, data in actions] == [
        f"menu compras {today.isoformat()} cena",
        f"menu otra {today.isoformat()} cena",
    ]

    assert "choclo" in seen["commands"].press(42, actions[0][1], who="Eze")
    seen["commands"].press(42, actions[1][1], who="Eze")
    assert seen["meal_store"].get(today, "cena").dish == "Tarta de acelga"


# --- el depurador ---


def test_the_cleaner_reaches_the_commands_and_cleans_the_one_database(
    wired, tmp_path, monkeypatch
):
    """Sin API, el depurador limpia avisos sobre la misma base y no tiene teles."""
    seen = _wired_commands(monkeypatch)
    run_main(monkeypatch, config_file(tmp_path, HOUSE))
    cleaner = seen["cleaner"]
    commands = seen["commands"]
    assert cleaner.tele is None
    assert cleaner.screens is None
    store = main.Store(tmp_path / "jobs.db")
    job = store.add(99, main.datetime.now() + timedelta(hours=1), "regar", repeat="daily")

    preview = cleaner.preview(42, "avisos")
    assert [candidate.job.id for candidate in preview.jobs] == [job.id]
    answer = commands.press(42, f"depurar ok {preview.token}", who="Eze")

    assert answer == "🧹 Borré 1 de 1."
    assert store.get(job.id) is None


def test_with_the_api_the_cleaner_shares_the_tele_link_and_the_screens(
    wired, tmp_path, monkeypatch
):
    seen = _wired_commands(monkeypatch)
    web = _wired_web(monkeypatch, tmp_path, HOUSE + "SCREEN_DEVICES=comedor\n")
    cleaner = seen["cleaner"]
    assert cleaner.tele is web.tele.link
    assert cleaner.screens is web.tele.screens
    cleaner.tele.store.save(Tele(
        "vieja", "0.1", 1, ("play",), main.datetime.now() - timedelta(days=8), "192.168.68.30"
    ))

    preview = cleaner.preview(42, "teles")
    assert seen["commands"].press(42, f"depurar ok {preview.token}") == "🧹 Borré 1 de 1."
    assert main.TeleStore(tmp_path / "jobs.db").get("vieja") is None

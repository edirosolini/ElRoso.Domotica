"""Run main()'s wiring end to end with stand-ins.

Two bugs already reached the container through this path: a renamed function
and a variable used before it existed. Neither showed up in a unit test,
because nothing exercised the assembly itself.
"""

import uuid

import pytest

from homeauto import main, polish


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
    monkeypatch.setattr(main, "build_speakers", lambda config, synth=None: _FakeRegistry())
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
    monkeypatch.setattr(main, "build_speakers", lambda config, synth=None: _FakeRegistry())
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
    monkeypatch.setattr(main, "build_speakers", lambda config, synth=None: _FakeRegistry())
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


def test_an_alarm_offers_to_be_postponed(wired, tmp_path, monkeypatch):
    seen = _spy_init(monkeypatch, main.Announcer)

    run_main(monkeypatch, config_file(tmp_path))

    assert seen["actions"] == main.SNOOZE_ACTIONS


def test_what_fired_is_kept_in_the_one_database(wired, tmp_path, monkeypatch):
    seen = _spy_init(monkeypatch, main.Reminders)

    run_main(monkeypatch, config_file(tmp_path))

    fired = seen["fired"]
    assert fired.db_path == tmp_path / "jobs.db"
    fired.remember(42, "arriba", None, main.datetime(2026, 9, 25, 7, 30))
    assert fired.last(42).message == "arriba"


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

from homeauto.bot.commands import Commands
from homeauto.weather import WeatherError

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42


class FakeWeather:
    def __init__(self, text="Ahora hay 14 grados, despejado.", boom=None):
        self.text = text
        self.boom = boom
        self.calls = 0

    def spoken(self):
        self.calls += 1
        if self.boom:
            raise self.boom
        return self.text


def build(weather=None, **speakers):
    speakers = speakers or {"parlante": FakeSpeaker("parlante")}
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        weather=weather or FakeWeather(),
    )
    return commands, speakers


def test_it_says_the_forecast_out_loud():
    cmd, spk = build()

    reply = cmd.weather(OWNER, "")

    assert spk["parlante"].said == ["Ahora hay 14 grados, despejado."]
    assert "14" in reply


def test_it_goes_to_the_device_you_asked_for():
    parlante, comedor = FakeSpeaker("parlante"), FakeSpeaker("comedor")
    cmd, _ = build(parlante=parlante, comedor=comedor)

    cmd.weather(OWNER, "en comedor")

    assert comedor.said and not parlante.said


def test_it_can_be_announced_everywhere():
    parlante, comedor = FakeSpeaker("parlante"), FakeSpeaker("comedor")
    cmd, _ = build(parlante=parlante, comedor=comedor)

    cmd.weather(OWNER, "en todos")

    assert parlante.said and comedor.said


def test_the_forecast_is_fetched_once_for_all_devices():
    weather = FakeWeather()
    cmd, _ = build(weather=weather, parlante=FakeSpeaker("parlante"), comedor=FakeSpeaker("comedor"))

    cmd.weather(OWNER, "en todos")

    assert weather.calls == 1, "una consulta, no una por equipo"


def test_a_weather_failure_is_explained_and_nothing_is_said():
    cmd, spk = build(weather=FakeWeather(boom=WeatherError("No pude consultar el clima: timeout")))

    reply = cmd.weather(OWNER, "")

    assert spk["parlante"].said == []
    assert "No pude consultar el clima" in reply


def test_a_stranger_gets_nothing():
    cmd, spk = build()

    cmd.weather(99, "")

    assert spk["parlante"].said == []

"""El resumen de la mañana: agenda, clima y lo que esté roto."""

from datetime import datetime

import pytest

from homeauto.briefing import Briefing
from homeauto.watch.status import Status

NOW = datetime(2026, 8, 31, 8, 0)


class FakeAgenda:
    def __init__(self, text="Hoy tenés dentista a las diez."):
        self.text = text

    def briefing(self):
        return self.text


class FakeWeather:
    def __init__(self, text="Ahora hay veinte grados, despejado."):
        self.text = text

    def spoken(self):
        return self.text


class FakeMonitor:
    def __init__(self, **up_by_name):
        self.state = up_by_name

    def snapshot(self):
        return {
            name: Status(name, up, 0, not up, "detalle", NOW)
            for name, up in self.state.items()
        }


class Broken:
    """Una fuente que se cae, para probar que no arrastra a las otras."""

    def briefing(self):
        raise RuntimeError("el calendario no contesta")

    def spoken(self):
        raise RuntimeError("el clima no contesta")

    def snapshot(self):
        raise RuntimeError("no hay chequeos")


def test_the_three_sources_end_up_in_one_text():
    briefing = Briefing(agenda=FakeAgenda(), weather=FakeWeather(), monitor=FakeMonitor(vpn=False))

    said = briefing.text()

    assert "dentista" in said
    assert "veinte grados" in said
    assert "vpn" in said


def test_the_agenda_goes_first():
    briefing = Briefing(agenda=FakeAgenda(), weather=FakeWeather())

    said = briefing.text()

    assert said.index("dentista") < said.index("veinte grados")


def test_services_that_are_up_are_not_mentioned():
    briefing = Briefing(weather=FakeWeather(), monitor=FakeMonitor(vpn=True, seq=True))

    assert briefing.text() == "Ahora hay veinte grados, despejado."


def test_several_services_down_are_named_together():
    briefing = Briefing(monitor=FakeMonitor(vpn=False, seq=False, backup=True))

    said = briefing.text()

    assert "vpn" in said and "seq" in said
    assert "backup" not in said


def test_a_broken_source_does_not_take_the_others_down():
    briefing = Briefing(agenda=Broken(), weather=FakeWeather(), monitor=Broken())

    assert briefing.text() == "Ahora hay veinte grados, despejado."


def test_missing_sources_are_simply_skipped():
    assert Briefing(weather=FakeWeather()).text() == "Ahora hay veinte grados, despejado."


def test_with_nothing_to_say_it_still_says_something():
    said = Briefing(agenda=Broken(), weather=Broken(), monitor=Broken()).text()

    assert said
    assert "resumen" in said.lower()


def test_no_digit_reaches_the_speaker():
    """Lo que arma el briefing se sintetiza: un dígito se leería mal."""
    briefing = Briefing(agenda=FakeAgenda(), weather=FakeWeather(), monitor=FakeMonitor(vpn=False))

    assert not any(char.isdigit() for char in briefing.text())

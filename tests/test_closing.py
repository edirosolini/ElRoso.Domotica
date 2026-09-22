"""El cierre del día: lo que viene mañana y lo que sigue roto."""

from datetime import datetime

from homeauto.closing import Closing
from homeauto.watch.status import Status

NOW = datetime(2026, 9, 22, 22, 0)


class FakeAgenda:
    """La agenda del día siguiente, como la pide el cierre."""

    def __init__(self, text="Mañana tenés una cosa. A las nueve, dentista."):
        self.text = text
        self.asked = []

    def spoken(self, when="", place=True):
        self.asked.append((when, place))
        return self.text


class FakeWeather:
    def __init__(self, text="Para mañana, máxima de veintiocho y mínima de dieciséis."):
        self.text = text

    def spoken_tomorrow(self):
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

    def spoken(self, when="", place=True):
        raise RuntimeError("el calendario no contesta")

    def spoken_tomorrow(self):
        raise RuntimeError("el clima no contesta")

    def snapshot(self):
        raise RuntimeError("no hay chequeos")


def test_the_three_sources_end_up_in_one_text():
    closing = Closing(agenda=FakeAgenda(), weather=FakeWeather(), monitor=FakeMonitor(vpn=False))

    said = closing.text()

    assert "dentista" in said
    assert "veintiocho" in said
    assert "vpn" in said


def test_tomorrow_goes_first():
    closing = Closing(agenda=FakeAgenda(), weather=FakeWeather())

    said = closing.text()

    assert said.index("dentista") < said.index("veintiocho")


def test_the_agenda_is_asked_for_tomorrow_without_the_place():
    """El lugar alarga lo que se escucha de corrido; /agenda lo sigue diciendo."""
    agenda = FakeAgenda()

    Closing(agenda=agenda).text()

    assert agenda.asked == [("mañana", False)]


def test_a_broken_source_does_not_take_the_others_down():
    closing = Closing(agenda=Broken(), weather=FakeWeather(), monitor=Broken())

    assert closing.text() == "Para mañana, máxima de veintiocho y mínima de dieciséis."


def test_missing_sources_are_simply_skipped():
    assert Closing(weather=FakeWeather()).text() == (
        "Para mañana, máxima de veintiocho y mínima de dieciséis."
    )


def test_with_nothing_to_say_it_stays_quiet():
    """A las once de la noche, un cierre vacío es ruido: mejor no hablar."""
    assert Closing(agenda=Broken(), weather=Broken(), monitor=Broken()).text() == ""


def test_services_that_are_up_are_not_mentioned():
    closing = Closing(weather=FakeWeather(), monitor=FakeMonitor(vpn=True, seq=True))

    assert closing.text() == "Para mañana, máxima de veintiocho y mínima de dieciséis."


def test_several_services_down_are_named_together():
    closing = Closing(monitor=FakeMonitor(vpn=False, seq=False, backup=True))

    said = closing.text()

    assert "vpn" in said and "seq" in said
    assert "backup" not in said


def test_no_digit_reaches_the_speaker():
    closing = Closing(agenda=FakeAgenda(), weather=FakeWeather(), monitor=FakeMonitor(vpn=False))

    assert not any(character.isdigit() for character in closing.text())


def test_the_trouble_line_is_reworded_keeping_the_names():
    closing = Closing(
        monitor=FakeMonitor(vpn=False),
        polish=lambda text, must_keep=(): f"[{'+'.join(must_keep)}] {text}",
    )

    assert closing.text().startswith("[vpn]")


def test_what_the_sources_already_polished_is_not_polished_again():
    """La agenda y el clima ya vienen reescritas por sus propias fuentes."""
    closing = Closing(
        agenda=FakeAgenda(),
        weather=FakeWeather(),
        polish=lambda text, must_keep=(): "REESCRITO",
    )

    assert "REESCRITO" not in closing.text()


# --- la lista de compras ----------------------------------------------------


class FakeLists:
    def __init__(self, *items, boom=None):
        self.stored = list(items)
        self.boom = boom

    def items(self, list_name):
        if self.boom:
            raise RuntimeError("la base no abre")
        return self.stored


def test_what_is_left_to_buy_is_counted_in_words():
    closing = Closing(lists=FakeLists("leche", "pan", "yerba"))

    said = closing.text()

    assert "tres cosas" in said
    assert "compras" in said


def test_one_thing_is_said_in_singular():
    assert "una cosa" in Closing(lists=FakeLists("leche")).text()


def test_an_empty_shopping_list_says_nothing():
    assert Closing(lists=FakeLists()).text() == ""


def test_a_broken_list_does_not_cost_the_rest():
    closing = Closing(weather=FakeWeather(), lists=FakeLists(boom=True))

    assert "veintiocho" in closing.text()


def test_the_shopping_list_goes_last():
    closing = Closing(agenda=FakeAgenda(), lists=FakeLists("leche"))

    said = closing.text()

    assert said.index("dentista") < said.index("compras")


def test_the_count_carries_no_digit():
    assert not any(c.isdigit() for c in Closing(lists=FakeLists(*["x"] * 21)).text())

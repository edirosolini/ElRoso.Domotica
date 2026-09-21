"""Lo que pasó de noche en Seq se recuerda a la mañana, no de madrugada."""

from datetime import datetime

from homeauto.briefing import Briefing
from homeauto.watch.seq import SeqEvent


class FakeNight:
    """Lo que dejaron los Seq durante la noche."""

    def __init__(self, *events, boom=None):
        self.events = list(events)
        self.boom = boom
        self.asked = 0

    def errors_since(self, since):
        self.asked += 1
        if self.boom:
            raise RuntimeError("Seq no contesta")
        return self.events


def error(app="Facturador.Backend", env="Production", message="explotó"):
    return SeqEvent(datetime(2026, 9, 22, 3, 0), "Error", message, app, env)


def test_a_quiet_night_says_nothing():
    briefing = Briefing(seq=FakeNight())

    assert "error" not in briefing.text().lower()


def test_the_night_errors_are_remembered_with_app_and_environment():
    briefing = Briefing(seq=FakeNight(error(), error()))

    said = briefing.text()

    assert "producción" in said.lower()
    assert "Facturador Backend" in said
    assert "noche" in said.lower()


def test_what_is_said_carries_no_digits():
    briefing = Briefing(seq=FakeNight(*[error() for _ in range(12)]))

    assert not any(c.isdigit() for c in briefing.text())


def test_a_seq_that_does_not_answer_does_not_cost_the_summary():
    briefing = Briefing(seq=FakeNight(boom=True), weather=type("W", (), {"spoken": lambda self: "Hay sol."})())

    assert "Hay sol." in briefing.text()


def test_the_detail_goes_to_the_chat_only():
    briefing = Briefing(seq=FakeNight(error(message="System.NullReferenceException en 1.24s")))

    summary = briefing.speech()

    assert "NullReference" in summary.written
    assert "NullReference" not in summary.spoken

from datetime import datetime, timedelta, timezone

from homeauto.watch.marks import Marks
from homeauto.watch.seq import SeqError, SeqEvent
from homeauto.watch.seq_watcher import SeqWatcher

NOW = datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc)


def error(message="algo falló", when=None):
    return SeqEvent(timestamp=when or NOW, level="Error", message=message)


class FakeSeq:
    def __init__(self, rounds=(), boom=None):
        self.rounds = list(rounds)
        self.boom = boom
        self.asked = []

    def errors_since(self, since):
        self.asked.append(since)
        if self.boom:
            raise self.boom
        return self.rounds.pop(0) if self.rounds else []


def build(tmp_path, rounds=(), boom=None, now=NOW, cooldown=15):
    said = []
    seq = FakeSeq(rounds, boom)
    watcher = SeqWatcher(
        client=seq,
        marks=Marks(tmp_path / "jobs.db"),
        announce=said.append,
        clock=lambda: now,
        cooldown_minutes=cooldown,
    )
    return watcher, seq, said


def test_no_errors_means_silence(tmp_path):
    watcher, _, said = build(tmp_path, rounds=[[]])

    watcher.check()

    assert said == []


def test_errors_are_announced(tmp_path):
    watcher, _, said = build(tmp_path, rounds=[[error("Se cayó la base")]])

    watcher.check()

    assert len(said) == 1
    assert "Se cayó la base" in said[0]


def test_the_first_look_goes_back_a_little(tmp_path):
    watcher, seq, _ = build(tmp_path, rounds=[[]])

    watcher.check()

    assert seq.asked[0] < NOW, "la primera vuelta tiene que mirar hacia atrás"


def test_the_next_look_starts_where_the_last_one_ended(tmp_path):
    watcher, seq, _ = build(tmp_path, rounds=[[], []])

    watcher.check()
    watcher.check()

    assert seq.asked[1] >= seq.asked[0]


def test_it_does_not_repeat_within_the_cooldown(tmp_path):
    watcher, _, said = build(tmp_path, rounds=[[error("uno")], [error("dos")]])

    watcher.check()
    watcher.check()

    assert len(said) == 1, "una tormenta de errores no puede ser una tormenta de avisos"


def test_after_the_cooldown_it_speaks_again(tmp_path):
    path = tmp_path / "jobs.db"
    said = []
    seq = FakeSeq([[error("uno")], [error("dos")]])

    for moment in (NOW, NOW + timedelta(minutes=20)):
        SeqWatcher(
            client=seq,
            marks=Marks(path),
            announce=said.append,
            clock=lambda m=moment: m,
            cooldown_minutes=15,
        ).check()

    assert len(said) == 2


def test_a_seq_failure_does_not_break_the_loop(tmp_path):
    watcher, _, said = build(tmp_path, boom=SeqError("clave rechazada"))

    watcher.check()  # no explota

    assert said == []


def test_the_state_survives_a_restart(tmp_path):
    path = tmp_path / "jobs.db"
    said = []
    seq = FakeSeq([[error("uno")], [error("dos")]])

    SeqWatcher(client=seq, marks=Marks(path), announce=said.append, clock=lambda: NOW).check()
    SeqWatcher(client=seq, marks=Marks(path), announce=said.append, clock=lambda: NOW).check()

    assert len(said) == 1, "reiniciar no puede saltear el enfriamiento"

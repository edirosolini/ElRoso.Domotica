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


def build(tmp_path, rounds=(), boom=None, now=NOW, cooldown=15, alias=""):
    said = []
    seq = FakeSeq(rounds, boom)
    watcher = SeqWatcher(
        client=seq,
        marks=Marks(tmp_path / "jobs.db"),
        announce=lambda text, detail="": said.append((text, detail)),
        clock=lambda: now,
        cooldown_minutes=cooldown,
        alias=alias,
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
    assert said[0][0] == "Hay un error nuevo en Seq."
    # La cita del log se escribe, no se dice.
    assert "Se cayó la base" in said[0][1]


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
            announce=lambda text, detail="": said.append((text, detail)),
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

    keep = lambda text, detail="": said.append((text, detail))
    SeqWatcher(client=seq, marks=Marks(path), announce=keep, clock=lambda: NOW).check()
    SeqWatcher(client=seq, marks=Marks(path), announce=keep, clock=lambda: NOW).check()

    assert len(said) == 1, "reiniciar no puede saltear el enfriamiento"


# --- varias instancias: un Seq por VPS -------------------------------------


def test_an_aliased_watcher_says_which_seq_it_is(tmp_path):
    watcher, _, said = build(tmp_path, rounds=[[error("Se cayó la base")]], alias="hosting")

    watcher.check()

    assert said[0][0] == "Hay un error nuevo en Seq de hosting."


def test_what_it_says_carries_no_digits(tmp_path):
    """🔴 Lo hablado va al sintetizador, y Piper lee un dígito como cardinal suelto."""
    watcher, _, said = build(tmp_path, rounds=[[error("x"), error("y")]], alias="hosting")

    watcher.check()

    assert not any(c.isdigit() for c in said[0][0]), said[0][0]


def test_two_instances_do_not_share_their_cooldown(tmp_path):
    """🔴 Un VPS ruidoso no puede tapar el aviso del otro: comparten archivo, no estado."""
    path = tmp_path / "jobs.db"
    said = []
    keep = lambda text, detail="": said.append((text, detail))

    for alias in ("hosting", "nube"):
        SeqWatcher(
            client=FakeSeq([[error("algo")]]),
            marks=Marks(path),
            announce=keep,
            clock=lambda: NOW,
            alias=alias,
        ).check()

    assert len(said) == 2, "cada instancia lleva su propio enfriamiento"
    assert "hosting" in said[0][0] and "nube" in said[1][0]


def test_two_instances_do_not_share_where_they_were_reading(tmp_path):
    path = tmp_path / "jobs.db"
    quiet = FakeSeq([[]])
    noisy = FakeSeq([[]])

    SeqWatcher(client=quiet, marks=Marks(path), announce=lambda *a, **k: None,
               clock=lambda: NOW, alias="hosting").check()
    SeqWatcher(client=noisy, marks=Marks(path), announce=lambda *a, **k: None,
               clock=lambda: NOW, alias="nube").check()

    assert noisy.asked[0] < NOW, "la primera vuelta de cada instancia mira hacia atrás sola"


def test_the_old_instance_keeps_its_marks(tmp_path):
    """Un despliegue nuevo no puede hacer que la instancia de siempre relea todo."""
    path = tmp_path / "jobs.db"
    marks = Marks(path)
    SeqWatcher(client=FakeSeq([[]]), marks=marks, announce=lambda *a, **k: None,
               clock=lambda: NOW).check()

    assert marks.get("seq:last_check") == NOW


def test_a_multi_word_alias_is_spoken_with_spaces(tmp_path):
    """🔴 "Seq de hosting_externo" dicho sería el guion bajo en el medio."""
    watcher, _, said = build(tmp_path, rounds=[[error("algo")]], alias="hosting_externo")

    watcher.check()

    assert said[0][0] == "Hay un error nuevo en Seq de hosting externo."
    assert "_" not in said[0][0]


def test_the_marks_keep_the_alias_as_written(tmp_path):
    """Lo hablado cambia; la clave de estado no, o se pierde dónde iba leyendo."""
    path = tmp_path / "jobs.db"
    marks = Marks(path)
    SeqWatcher(client=FakeSeq([[]]), marks=marks, announce=lambda *a, **k: None,
               clock=lambda: NOW, alias="hosting_externo").check()

    assert marks.get("seq:hosting_externo:last_check") == NOW

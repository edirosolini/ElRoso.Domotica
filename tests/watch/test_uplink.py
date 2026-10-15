"""El corte de internet: cuándo se declara, qué se dice y qué queda escrito."""

from datetime import datetime, timedelta

from homeauto.watch.marks import Marks
from homeauto.watch.uplink import ALERTED, DOWN_SINCE, TARGETS, Uplink

START = datetime(2026, 10, 15, 14, 12)
MINUTE = timedelta(minutes=1)


class Net:
    """Un destino por (host, port); `alive` dice cuáles contestan esta ronda."""

    def __init__(self):
        self.alive = set(TARGETS)
        self.tried = []

    def connect(self, host, port, timeout):
        self.tried.append((host, port, timeout))
        if (host, port) not in self.alive:
            raise OSError("unreachable")
        return 0.01


def build(tmp_path, moment=None):
    net = Net()
    now = moment if moment is not None else [START]
    spoken, written = [], []
    marks = Marks(tmp_path / "jobs.db")
    watcher = Uplink(
        marks=marks,
        speak=spoken.append,
        tell=written.append,
        connect=net.connect,
        clock=lambda: now[0],
    )
    return watcher, net, marks, now, spoken, written


def test_the_targets_are_fixed_ipv4_addresses():
    assert TARGETS == (("1.1.1.1", 443), ("8.8.8.8", 443), ("9.9.9.9", 443))


def test_one_live_target_is_enough(tmp_path):
    watcher, net, marks, _, spoken, written = build(tmp_path)
    net.alive = {("9.9.9.9", 443)}

    assert watcher.run_once() is True
    assert watcher.online is True
    assert marks.get(DOWN_SINCE) is None
    assert spoken == [] and written == []


def test_the_timeout_is_short(tmp_path):
    watcher, net, *_ = build(tmp_path)
    net.alive = set()

    watcher.run_once()

    assert net.tried and all(timeout <= 5 for _, _, timeout in net.tried)


def test_a_live_target_stops_the_round(tmp_path):
    watcher, net, *_ = build(tmp_path)

    watcher.run_once()

    assert len(net.tried) == 1


def test_one_failed_round_is_not_an_outage_but_marks_when_it_began(tmp_path):
    watcher, net, marks, _, spoken, written = build(tmp_path)
    net.alive = set()

    assert watcher.run_once() is False
    assert watcher.online is False
    assert marks.get(DOWN_SINCE) == START
    assert marks.get(ALERTED) is None
    assert spoken == [] and written == []


def test_two_failed_rounds_declare_the_outage_once(tmp_path):
    watcher, net, marks, now, spoken, written = build(tmp_path)
    net.alive = set()

    watcher.run_once()
    now[0] += MINUTE
    watcher.run_once()
    now[0] += MINUTE
    watcher.run_once()

    assert spoken == ["Se cortó internet."], "se dice una sola vez, sin re-aviso"
    assert written == [], "sin internet no hay chat"
    assert marks.get(DOWN_SINCE) == START, "la duración se cuenta desde la primera ronda"
    assert marks.get(ALERTED) is not None


def test_a_short_blip_says_nothing_when_it_comes_back(tmp_path):
    watcher, net, marks, now, spoken, written = build(tmp_path)
    net.alive = set()
    watcher.run_once()

    net.alive = set(TARGETS)
    now[0] += MINUTE
    watcher.run_once()

    assert spoken == [] and written == []
    assert marks.get(DOWN_SINCE) is None


def test_the_comeback_says_how_long_it_was_out(tmp_path):
    watcher, net, marks, now, spoken, written = build(tmp_path)
    net.alive = set()
    watcher.run_once()
    now[0] += MINUTE
    watcher.run_once()

    net.alive = set(TARGETS)
    now[0] = START + timedelta(minutes=20)
    assert watcher.run_once() is True

    assert spoken[-1] == "Volvió internet. Estuvo cortado veinte minutos."
    assert written == ["🌐 Internet se cortó de 14:12 a 14:32 (20 min)"]
    assert marks.get(DOWN_SINCE) is None
    assert marks.get(ALERTED) is None


def test_the_comeback_is_said_without_digits(tmp_path):
    watcher, net, _, now, spoken, _ = build(tmp_path)
    net.alive = set()
    watcher.run_once()
    now[0] += MINUTE
    watcher.run_once()
    net.alive = set(TARGETS)
    now[0] = START + timedelta(minutes=95)
    watcher.run_once()

    assert not any(char.isdigit() for text in spoken for char in text)


def test_a_restart_in_the_middle_of_an_outage_keeps_when_it_began(tmp_path):
    first, net, _, _, _, _ = build(tmp_path)
    net.alive = set()
    first.run_once()

    later = [START + timedelta(minutes=3)]
    second, net, marks, _, spoken, _ = build(tmp_path, moment=later)
    net.alive = set()
    second.run_once()

    assert spoken == ["Se cortó internet."]
    assert marks.get(DOWN_SINCE) == START


def test_a_speaker_that_fails_does_not_lose_the_state(tmp_path):
    watcher, net, marks, now, _, _ = build(tmp_path)

    def broken(text):
        raise RuntimeError("no speaker")

    watcher.speak = broken
    net.alive = set()
    watcher.run_once()
    now[0] += MINUTE
    watcher.run_once()

    assert marks.get(ALERTED) is not None


def test_marks_can_forget_a_key(tmp_path):
    marks = Marks(tmp_path / "jobs.db")
    marks.set("a", START)
    marks.set("b", START)

    marks.clear("a")

    assert marks.get("a") is None
    assert marks.get("b") == START

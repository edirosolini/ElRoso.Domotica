"""Un recordatorio que sonó y nadie marcó vuelve a avisar por el chat y por el parlante."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from homeauto.people import Person
from homeauto.polish import as_is
from homeauto.schedule.announcer import Announcer
from homeauto.schedule.awaiting import AwaitingStore
from homeauto.schedule.fired import FiredStore
from homeauto.schedule.reminders import NAG_DELAY, NAG_LIMIT, SNOOZE_WINDOW, Reminders
from homeauto.schedule.store import EVERYONE, PERSON, REMINDER, Store
from homeauto.voice import chime
from homeauto.voice.caster import CastError
from tests.conftest import FakeSpeaker, StubRegistry

OWNER = 42
OTHER = 99
NOW = datetime(2026, 10, 5, 8, 0)
SOON = NOW + timedelta(minutes=5)

DONE = (("✅ Hecho", "hecho {job}"),)


class FakeTimer:
    def __init__(self):
        self.armed = {}

    def schedule(self, key, when, action):
        self.armed[key] = (when, action)

    def unschedule(self, key):
        self.armed.pop(key, None)

    def fire(self, key):
        self.armed[key][1]()


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def nag_key(job):
    return f"nag:{job.id}"


@pytest.fixture
def parts(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    clock = Clock(NOW)
    told = []
    announced = []

    def notify(chat_id, text, actions=()):
        told.append((chat_id, text, actions))

    def build(chat_ids=(OWNER, OTHER), notify=notify):
        return Reminders(
            store=Store(path),
            timer=timer,
            announce=announced.append,
            fired=FiredStore(path),
            awaiting=AwaitingStore(path),
            notify=notify,
            clock=clock,
            chat_ids=chat_ids,
            nag_actions=DONE,
        )

    return build, timer, clock, told, announced, path


def ring(reminders, timer, clock, **kwargs):
    job = reminders.add(OWNER, SOON, kwargs.pop("message", "la pastilla"), **kwargs)
    clock.now = SOON
    timer.fire(str(job.id))
    return job


def nag(timer, clock, job):
    when, action = timer.armed.pop(nag_key(job))
    clock.now = when
    action()


# --- cuándo -----------------------------------------------------------------


def test_a_reminder_that_rang_arms_its_nag(parts):
    build, timer, clock, *_ = parts
    job = ring(build(), timer, clock, kind=REMINDER)

    assert timer.armed[nag_key(job)][0] == SOON + NAG_DELAY


def test_an_alarm_never_nags(parts):
    build, timer, clock, *_ = parts
    job = ring(build(), timer, clock)

    assert nag_key(job) not in timer.armed


def test_the_nag_keeps_its_own_key_when_a_daily_rearms(parts):
    build, timer, clock, *_ = parts
    job = ring(build(), timer, clock, kind=REMINDER, repeat="daily")

    assert str(job.id) in timer.armed
    assert nag_key(job) in timer.armed


def test_it_nags_every_five_minutes_and_stops_after_the_limit(parts):
    build, timer, clock, told, *_ = parts
    job = ring(build(), timer, clock, kind=REMINDER)

    moments = []
    while nag_key(job) in timer.armed:
        nag(timer, clock, job)
        moments.append(clock.now)

    assert NAG_LIMIT == 3
    assert moments == [SOON + NAG_DELAY * n for n in (1, 2, 3)]
    assert len(told) == NAG_LIMIT * 2


# --- qué dice y a quién -------------------------------------------------------


def test_the_nag_goes_to_every_chat_with_only_the_done_button(parts):
    build, timer, clock, told, announced, _ = parts
    job = ring(build(), timer, clock, kind=REMINDER)
    announced.clear()

    nag(timer, clock, job)

    assert told == [
        (OWNER, "🔔 Sigue pendiente: «la pastilla»", (("✅ Hecho", f"hecho {job.id}"),)),
        (OTHER, "🔔 Sigue pendiente: «la pastilla»", (("✅ Hecho", f"hecho {job.id}"),)),
    ]
    assert announced == []


def test_a_broken_chat_does_not_stop_the_others(parts):
    build, timer, clock, *_ = parts
    reached = []

    def notify(chat_id, text, actions=()):
        if chat_id == OWNER:
            raise RuntimeError("chat roto")
        reached.append(chat_id)

    job = ring(build(notify=notify), timer, clock, kind=REMINDER)

    nag(timer, clock, job)

    assert reached == [OTHER]
    assert nag_key(job) in timer.armed


def test_without_a_list_it_nags_the_chat_that_asked(parts):
    build, timer, clock, told, *_ = parts
    job = ring(build(chat_ids=()), timer, clock, kind=REMINDER)

    nag(timer, clock, job)

    assert [chat for chat, *_ in told] == [OWNER]


# --- qué lo corta -------------------------------------------------------------


def test_done_unschedules_the_nag(parts):
    build, timer, clock, told, *_ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)

    reminders.done(OWNER, job.id, "Eze")

    assert nag_key(job) not in timer.armed


def test_a_nag_that_was_already_due_says_nothing_after_done(parts):
    build, timer, clock, told, *_ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)
    _, action = timer.armed[nag_key(job)]
    reminders.done(OWNER, job.id, "Eze")
    told.clear()

    action()

    assert told == []


def test_snoozing_closes_the_original_and_the_snoozed_one_nags_when_it_rings(parts):
    build, timer, clock, told, *_ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)

    later = reminders.snooze(OWNER, timedelta(minutes=10))

    assert nag_key(job) not in timer.armed
    assert reminders.done(OWNER, job.id, "Eze") is None
    clock.now = later.when
    timer.fire(str(later.id))
    assert timer.armed[nag_key(later)][0] == later.when + NAG_DELAY


def test_cancelling_a_reminder_that_rang_closes_the_wait(parts):
    build, timer, clock, *_ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER, repeat="daily")

    assert reminders.cancel(OWNER, job.id)

    assert nag_key(job) not in timer.armed
    assert reminders.done(OWNER, job.id, "Eze") is None


# --- después de un reinicio ---------------------------------------------------


def test_a_restart_rearms_a_pending_nag(parts):
    build, timer, clock, *_ = parts
    job = ring(build(), timer, clock, kind=REMINDER)
    timer.armed.clear()

    build().start(now=SOON + timedelta(minutes=1))

    assert timer.armed[nag_key(job)][0] == SOON + NAG_DELAY


def test_a_nag_missed_while_down_goes_out_on_start(parts):
    build, timer, clock, told, *_ = parts
    job = ring(build(), timer, clock, kind=REMINDER)
    timer.armed.clear()
    clock.now = SOON + timedelta(minutes=12)

    build().start(now=clock.now)

    assert [text for _, text, _ in told] == ["🔔 Sigue pendiente: «la pastilla»"] * 2
    assert timer.armed[nag_key(job)][0] == clock.now + NAG_DELAY


def test_a_nag_missed_past_the_window_is_dropped(parts):
    build, timer, clock, told, *_ = parts
    reminders = build()
    job = ring(reminders, timer, clock, kind=REMINDER)
    timer.armed.clear()
    clock.now = SOON + SNOOZE_WINDOW + timedelta(minutes=1)

    build().start(now=clock.now)

    assert told == []
    assert nag_key(job) not in timer.armed
    assert reminders.done(OWNER, job.id, "Eze") == "la pastilla"


def test_a_wait_from_before_the_nags_never_nags(parts):
    """Lo que ya esperaba en una tabla sin las columnas del re-aviso no re-avisa."""
    build, timer, clock, told, _, path = parts
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE awaiting_done (job_id INTEGER PRIMARY KEY, message TEXT NOT NULL,"
        " fired_at TEXT NOT NULL);"
    )
    conn.execute(
        "INSERT INTO awaiting_done VALUES (?, ?, ?)", (7, "la pastilla", NOW.isoformat())
    )
    conn.commit()
    conn.close()

    build().start(now=NOW + timedelta(minutes=6))

    assert told == []
    assert "nag:7" not in timer.armed


# --- la tabla -----------------------------------------------------------------


def test_the_wait_counts_its_nags(tmp_path):
    awaiting = AwaitingStore(tmp_path / "jobs.db")
    awaiting.remember(1, "la pastilla", NOW, next_nag=NOW + NAG_DELAY)

    awaiting.mark_nagged(1, NOW + NAG_DELAY * 2)

    wait = awaiting.get(1)
    assert wait.message == "la pastilla"
    assert wait.fired_at == NOW
    assert wait.nags == 1
    assert wait.next_nag == NOW + NAG_DELAY * 2
    assert [w.job_id for w in awaiting.due_nags()] == [1]


def test_a_wait_without_a_next_nag_is_not_due(tmp_path):
    awaiting = AwaitingStore(tmp_path / "jobs.db")
    awaiting.remember(1, "la pastilla", NOW, next_nag=NOW + NAG_DELAY)

    awaiting.mark_nagged(1, None)

    assert awaiting.due_nags() == []
    assert awaiting.take(1) == "la pastilla"


def test_ringing_again_restarts_the_count(tmp_path):
    awaiting = AwaitingStore(tmp_path / "jobs.db")
    awaiting.remember(1, "la pastilla", NOW, next_nag=NOW + NAG_DELAY)
    awaiting.mark_nagged(1, None)

    awaiting.remember(1, "la pastilla", NOW + timedelta(days=1) - timedelta(hours=1),
                      next_nag=NOW + timedelta(days=1))

    assert awaiting.get(1).nags == 0


def test_fired_remembers_which_job_rang(tmp_path):
    fired = FiredStore(tmp_path / "jobs.db")

    fired.remember(OWNER, "la pastilla", None, NOW, REMINDER, job_id=7)

    assert fired.last(OWNER).job_id == 7


def test_an_old_fired_table_gets_the_job_column(tmp_path):
    path = tmp_path / "jobs.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE last_fired (chat_id INTEGER PRIMARY KEY, message TEXT NOT NULL,"
        " device TEXT, fired_at TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'alarm');"
    )
    conn.execute(
        "INSERT INTO last_fired (chat_id, message, fired_at) VALUES (?, ?, ?)",
        (OWNER, "arriba", NOW.isoformat()),
    )
    conn.commit()
    conn.close()

    assert FiredStore(path).last(OWNER).job_id is None


# --- en el parlante -----------------------------------------------------------


class Quiet:
    """Un silencio fijo, con la forma de `Hush`."""

    def __init__(self, quiet=False, away=False):
        self.quiet = quiet
        self.away = away

    def is_quiet(self, moment):
        return self.quiet or self.away

    def is_away(self, moment=None):
        return self.away

    def reason(self, moment=None):
        return "De vacaciones" if self.away else "Horario de descanso"


@pytest.fixture
def voiced(tmp_path):
    path = tmp_path / "jobs.db"
    timer = FakeTimer()
    clock = Clock(NOW)
    told = []
    speakers = {"parlante": FakeSpeaker("parlante"), "cocina": FakeSpeaker("cocina")}
    people = {5: Person(5, "Cin", None)}

    def notify(chat_id, text, actions=()):
        told.append((chat_id, text, actions))

    def build(quiet=None, polish=as_is, fail=None, broken_voice=False):
        if fail is not None:
            for speaker in speakers.values():
                speaker.fail = fail
        announcer = Announcer(
            speakers=StubRegistry(**speakers),
            notify=notify,
            fallback="parlante",
            quiet=quiet,
            clock=clock,
            polish=polish,
            chat_ids=(OWNER, OTHER),
        )

        def broken(job):
            raise RuntimeError("se cayó la voz")

        return Reminders(
            store=Store(path),
            timer=timer,
            announce=announcer,
            say_nag=broken if broken_voice else announcer.nag,
            fired=FiredStore(path),
            awaiting=AwaitingStore(path),
            notify=notify,
            clock=clock,
            chat_ids=(OWNER, OTHER),
            nag_actions=DONE,
            quiet=quiet,
            resolve=people.get,
            find=lambda name: next((p for p in people.values() if p.name == name), None),
        )

    return build, timer, clock, told, speakers


def heard(speakers):
    """Lo dicho por cada equipo, olvidando lo dicho hasta ahora."""
    said = {name: list(speaker.said) for name, speaker in speakers.items()}
    for speaker in speakers.values():
        speaker.said.clear()
        speaker.chimes.clear()
        speaker.min_volumes.clear()
    return said


def test_the_nag_is_said_on_the_devices_of_the_reminder(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER, device="cocina")
    heard(speakers)

    nag(timer, clock, job)

    assert heard(speakers) == {"parlante": [], "cocina": ["Sigue pendiente: la pastilla."]}


def test_the_nag_sounds_like_a_reminder(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER)
    heard(speakers)

    nag(timer, clock, job)

    speaker = speakers["parlante"]
    assert speaker.said == ["Sigue pendiente: la pastilla."]
    assert speaker.chimes == [chime.SOFT]
    assert speaker.min_volumes == [None], "None es el piso propio del equipo, sesenta"
    assert not any(char.isdigit() for char in speaker.said[0])


def test_the_nag_calls_the_name_between_brackets(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER, message="[Papá] tomar la pastilla")
    heard(speakers)

    nag(timer, clock, job)

    assert speakers["parlante"].said == ["Papá, sigue pendiente: tomar la pastilla."]


def test_the_nag_calls_the_person_it_was_for(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER, assignee=PERSON, assignee_id=5)
    heard(speakers)

    nag(timer, clock, job)

    assert speakers["parlante"].said == ["Cin, sigue pendiente: la pastilla."]


def test_the_nag_calls_everyone(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER, assignee=EVERYONE)
    heard(speakers)

    nag(timer, clock, job)

    assert speakers["parlante"].said == ["Todos, sigue pendiente: la pastilla."]


def test_the_nag_calls_whose_turn_it_is(voiced):
    build, timer, clock, told, speakers = voiced
    reminders = build()
    job = reminders.add(OWNER, SOON, "sacar la basura", repeat="daily", kind=REMINDER)
    reminders.set_rota(job.id, ["Die"], SOON.date())
    clock.now = SOON
    timer.fire(str(job.id))
    heard(speakers)

    nag(timer, clock, job)

    assert speakers["parlante"].said == ["Die, sigue pendiente: sacar la basura."]


def test_the_turn_wins_over_the_name_between_brackets(voiced):
    build, timer, clock, told, speakers = voiced
    reminders = build()
    job = reminders.add(OWNER, SOON, "[Papá] tomar", repeat="daily", kind=REMINDER)
    reminders.set_rota(job.id, ["Die"], SOON.date())
    clock.now = SOON
    timer.fire(str(job.id))
    heard(speakers)

    nag(timer, clock, job)

    assert speakers["parlante"].said == ["Die, sigue pendiente: Papá, tomar."]


def test_the_nag_is_not_polished(voiced):
    build, timer, clock, told, speakers = voiced
    polished = lambda text, must_keep=(): f"Es hora de: {text}"
    job = ring(build(polish=polished), timer, clock, kind=REMINDER)
    assert heard(speakers)["parlante"] == ["Es hora de: la pastilla"]

    nag(timer, clock, job)

    assert speakers["parlante"].said == ["Sigue pendiente: la pastilla."]


@pytest.mark.parametrize("quiet", [Quiet(quiet=True), Quiet(away=True)], ids=["rest", "away"])
def test_resting_or_away_the_nag_is_only_written(voiced, quiet):
    build, timer, clock, told, speakers = voiced
    job = ring(build(quiet=quiet), timer, clock, kind=REMINDER)
    heard(speakers)
    told.clear()

    nag(timer, clock, job)

    assert heard(speakers) == {"parlante": [], "cocina": []}
    assert [text for _, text, _ in told] == ["🔔 Sigue pendiente: «la pastilla»"] * 2


def test_a_broken_speaker_does_not_stop_the_chat(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(fail=CastError("parlante apagado")), timer, clock, kind=REMINDER)
    told.clear()

    nag(timer, clock, job)

    assert [text for _, text, _ in told] == ["🔔 Sigue pendiente: «la pastilla»"] * 2
    assert nag_key(job) in timer.armed


def test_a_broken_voice_does_not_stop_the_chat(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(broken_voice=True), timer, clock, kind=REMINDER)
    told.clear()

    nag(timer, clock, job)

    assert [chat for chat, *_ in told] == [OWNER, OTHER]
    assert nag_key(job) in timer.armed


def test_every_nag_is_said_up_to_the_last(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER, device="cocina")
    heard(speakers)

    while nag_key(job) in timer.armed:
        nag(timer, clock, job)

    assert heard(speakers)["cocina"] == ["Sigue pendiente: la pastilla."] * NAG_LIMIT


def test_a_nag_missed_while_down_is_said_on_start_on_the_devices_it_rang(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER, device="cocina")
    assert build().store.get(job.id) is None, "el timer se borra al sonar"
    timer.armed.clear()
    heard(speakers)
    clock.now = SOON + timedelta(minutes=7)

    build().start(now=clock.now)

    assert heard(speakers)["cocina"] == ["Sigue pendiente: la pastilla."]


def test_a_nag_missed_while_down_is_not_said_resting(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER)
    timer.armed.clear()
    heard(speakers)
    told.clear()
    clock.now = SOON + timedelta(minutes=7)

    build(quiet=Quiet(quiet=True)).start(now=clock.now)

    assert heard(speakers) == {"parlante": [], "cocina": []}
    assert len(told) == 2


def written(told):
    """Los textos escritos, sin repetir los de cada chat."""
    return list(dict.fromkeys(text for _, text, _ in told))


@pytest.mark.parametrize(
    ("message", "kwargs", "expected"),
    [
        ("tomar medicación", {"assignee": PERSON, "assignee_id": 5},
         "🔔 Cin, sigue pendiente: «tomar medicación»"),
        ("la pastilla", {"assignee": EVERYONE}, "🔔 Todos, sigue pendiente: «la pastilla»"),
        ("[Papá] tomar la pastilla", {}, "🔔 Papá, sigue pendiente: «tomar la pastilla»"),
        ("la pastilla", {}, "🔔 Sigue pendiente: «la pastilla»"),
    ],
    ids=["person", "everyone", "brackets", "nobody"],
)
def test_the_written_nag_calls_the_same_name_as_the_spoken_one(voiced, message, kwargs, expected):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER, message=message, **kwargs)
    told.clear()

    nag(timer, clock, job)

    assert written(told) == [expected]


def test_the_written_nag_calls_whose_turn_it_is(voiced):
    build, timer, clock, told, speakers = voiced
    reminders = build()
    job = reminders.add(OWNER, SOON, "sacar la basura", repeat="daily", kind=REMINDER)
    reminders.set_rota(job.id, ["Die"], SOON.date())
    clock.now = SOON
    timer.fire(str(job.id))
    told.clear()

    nag(timer, clock, job)

    assert written(told) == ["🔔 Die, sigue pendiente: «sacar la basura»"]


def test_the_written_nag_after_a_restart_calls_the_person(voiced):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER, assignee=PERSON, assignee_id=5)
    timer.armed.clear()
    told.clear()
    clock.now = SOON + timedelta(minutes=7)

    build().start(now=clock.now)

    assert written(told) == ["🔔 Cin, sigue pendiente: «la pastilla»"]


def test_a_wait_from_before_the_devices_is_said_on_the_devices_of_the_job(voiced, tmp_path):
    build, timer, clock, told, speakers = voiced
    job = ring(build(), timer, clock, kind=REMINDER, device="cocina", repeat="daily")
    conn = sqlite3.connect(tmp_path / "jobs.db")
    conn.execute("UPDATE awaiting_done SET devices = NULL")
    conn.commit()
    conn.close()
    heard(speakers)

    nag(timer, clock, job)

    assert heard(speakers)["cocina"] == ["Sigue pendiente: la pastilla."]


def test_the_wait_keeps_the_devices_it_rang_on(tmp_path):
    awaiting = AwaitingStore(tmp_path / "jobs.db")

    awaiting.remember(1, "la pastilla", NOW, devices="cocina,comedor")

    assert awaiting.get(1).devices == "cocina,comedor"


def test_an_old_wait_table_gets_the_devices_column(tmp_path):
    path = tmp_path / "jobs.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE awaiting_done (job_id INTEGER PRIMARY KEY, message TEXT NOT NULL,"
        " fired_at TEXT NOT NULL);"
    )
    conn.execute("INSERT INTO awaiting_done VALUES (?, ?, ?)", (7, "la pastilla", NOW.isoformat()))
    conn.commit()
    conn.close()

    assert AwaitingStore(path).get(7).devices is None

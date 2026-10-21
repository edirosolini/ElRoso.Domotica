from datetime import datetime

import pytest

from homeauto.schedule.announcer import Announcer
from homeauto.schedule.store import REMINDER, Job
from homeauto.voice.caster import CastError
from homeauto.voice.speaker import ALARM_MIN_VOLUME
from homeauto.voice import chime
from homeauto.voice.tts import TtsError

JOB = Job(id=7, chat_id=42, when=datetime(2026, 8, 30, 7, 30), message="arriba")


from tests.conftest import FakeSpeaker, StubRegistry


def build(fail=None):
    speaker = FakeSpeaker("parlante", fail)
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda chat_id, text: sent.append((chat_id, text)),
        fallback="parlante",
    )
    return announcer, speaker, sent


def test_says_it_out_loud():
    announcer, speaker, _ = build()

    announcer(JOB)

    assert speaker.said == ["arriba"]


def test_an_alarm_wakes_with_its_own_beeps_and_floor():
    announcer, speaker, _ = build()

    announcer(JOB)

    assert speaker.chimes == [chime.WAKE]
    assert speaker.min_volumes == [ALARM_MIN_VOLUME]


@pytest.mark.parametrize("repeat", ["once", "daily"])
def test_a_reminder_or_timer_keeps_the_soft_beep_and_the_usual_floor(repeat):
    announcer, speaker, _ = build()

    reminder = Job(
        id=8, chat_id=42, when=JOB.when, message="la pastilla", repeat=repeat, kind=REMINDER
    )

    announcer(reminder)

    assert speaker.chimes == [chime.SOFT]
    assert speaker.min_volumes == [None], "None es el piso propio del equipo, sesenta"


def test_also_writes_to_the_chat():
    announcer, _, sent = build()

    announcer(JOB)

    assert len(sent) == 1
    chat_id, text = sent[0]
    assert chat_id == 42
    assert "arriba" in text


@pytest.mark.parametrize("failure", [CastError("parlante apagado"), TtsError("piper falló")])
def test_chat_still_gets_it_when_the_speaker_fails(failure):
    announcer, _, sent = build(fail=failure)

    announcer(JOB)

    assert len(sent) == 1, "si no suena, el aviso tiene que llegar igual al teléfono"
    _, text = sent[0]
    assert "arriba" in text


def test_the_chat_is_told_that_it_did_not_sound():
    announcer, _, sent = build(fail=CastError("parlante apagado"))

    announcer(JOB)

    _, text = sent[0]
    assert "parlante apagado" in text
    assert "no pude" in text.lower()


def test_a_broken_chat_does_not_stop_the_voice():
    speaker = FakeSpeaker("parlante")

    def notify(chat_id, text):
        raise RuntimeError("telegram caído")

    Announcer(speakers=StubRegistry(parlante=speaker), notify=notify, fallback="parlante")(JOB)

    assert speaker.said == ["arriba"], "el parlante ya habló: un fallo de Telegram no lo deshace"


def test_daily_jobs_are_marked_as_such():
    daily = Job(id=8, chat_id=42, when=JOB.when, message="arriba", repeat="daily")
    announcer, _, sent = build()

    announcer(daily)

    _, text = sent[0]
    assert "todos los días" in text.lower()


def test_it_speaks_on_the_device_the_job_asked_for():
    parlante, tv = FakeSpeaker("parlante"), FakeSpeaker("tv")
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=parlante, tv=tv),
        notify=lambda chat_id, text: sent.append((chat_id, text)),
        fallback="parlante",
    )

    announcer(Job(id=1, chat_id=42, when=JOB.when, message="que bajen", device="tv"))

    assert tv.said == ["que bajen"] and parlante.said == []


def test_a_job_without_a_device_falls_back():
    parlante, tv = FakeSpeaker("parlante"), FakeSpeaker("tv")
    announcer = Announcer(
        speakers=StubRegistry(parlante=parlante, tv=tv),
        notify=lambda chat_id, text: None,
        fallback="parlante",
    )

    announcer(Job(id=1, chat_id=42, when=JOB.when, message="viejo", device=None))

    assert parlante.said == ["viejo"]


def test_a_device_that_no_longer_exists_still_reaches_the_chat():
    """Un job viejo puede apuntar a un alias que se sacó de la config."""
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        notify=lambda chat_id, text: sent.append((chat_id, text)),
        fallback="parlante",
    )

    announcer(Job(id=1, chat_id=42, when=JOB.when, message="hola", device="cocina"))

    assert len(sent) == 1
    assert "cocina" in sent[0][1]


def test_weekly_alarm_says_which_days_it_repeats():
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=FakeSpeaker()),
        notify=lambda chat_id, text: sent.append(text),
        fallback="parlante",
    )

    announcer(Job(id=1, chat_id=42, when=JOB.when, message="arriba", repeat="weekly", days="1,3,5"))

    assert "lun, mié, vie" in sent[0]


def test_the_message_is_reworded_before_being_said():
    speaker = FakeSpeaker("parlante")
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda chat_id, text: sent.append(text),
        fallback="parlante",
        polish=lambda text, must_keep=(): f"Te recuerdo: {text}",
    )

    announcer(JOB)

    assert speaker.said == ["Te recuerdo: arriba"]
    assert "Te recuerdo: arriba" in sent[0], "el chat dice lo mismo que el parlante"


# --- acciones del aviso ----------------------------------------------------


def test_the_chat_gets_the_actions_when_there_are_some():
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        notify=lambda chat_id, text, actions=(): sent.append(actions),
        fallback="parlante",
        actions=(("Posponer 10 min", "posponer 10m"),),
    )

    announcer(JOB)

    assert sent == [(("Posponer 10 min", "posponer 10m"),)]


def test_without_actions_the_chat_gets_plain_text():
    """HouseVoice y la API usan el mismo notificador con dos argumentos."""
    announcer, _, sent = build()

    announcer(JOB)

    assert len(sent) == 1


def test_the_alarm_actions_carry_its_number():
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        notify=lambda chat_id, text, actions=(): sent.append(actions),
        fallback="parlante",
        actions=(("🔕 Apagar", "callar {job}"), ("Posponer 10 min", "posponer 10m")),
    )

    announcer(JOB)

    assert sent == [(("🔕 Apagar", "callar 7"), ("Posponer 10 min", "posponer 10m"))]


# --- la alarma que sigue sonando -------------------------------------------


class Quiet:
    label = "22:00–05:25"

    def __init__(self, quiet):
        self.quiet = quiet

    def is_quiet(self, _now):
        return self.quiet


def ringing(quiet=False):
    speaker = FakeSpeaker("parlante")
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda chat_id, text, actions=(): sent.append((chat_id, text, actions)),
        fallback="parlante",
        quiet=Quiet(quiet),
        actions=(("🔕 Apagar", "callar {job}"), ("Posponer 10 min", "posponer 10m")),
        ring_actions=(("🔕 Apagar", "callar {job}"),),
        chat_ids=(42, 99),
    )
    return announcer, speaker, sent


@pytest.mark.parametrize(
    "rings, level", [(1, chime.WAKE_LEVELS[1]), (2, chime.WAKE_LEVELS[2]), (9, chime.WAKE_LEVELS[2])]
)
def test_each_repetition_wakes_louder_with_the_alarm_floor(rings, level):
    announcer, speaker, _ = ringing()

    announcer(JOB, rings=rings)

    assert speaker.said == ["arriba"]
    assert speaker.chimes == [level]
    assert speaker.min_volumes == [ALARM_MIN_VOLUME]


def test_every_repetition_says_it_keeps_ringing_with_the_off_button():
    announcer, _, sent = ringing()

    announcer(JOB, rings=1)

    assert [chat for chat, *_ in sent] == [42, 99]
    _, text, actions = sent[0]
    assert text.startswith("⏰ Sigue sonando: «arriba»")
    assert actions == (("🔕 Apagar", "callar 7"),)


def test_in_the_quiet_hours_a_repetition_only_writes():
    announcer, speaker, sent = ringing(quiet=True)

    announcer(JOB, rings=1)
    announcer(JOB, rings=2)

    assert speaker.said == []
    assert len(sent) == 4, "una por chat en cada repetición"
    assert "Sigue sonando" in sent[0][1]
    assert "Horario de descanso" in sent[0][1]


def test_the_alarm_stops_on_its_devices():
    cocina = FakeSpeaker("cocina")
    parlante = FakeSpeaker("parlante")
    announcer = Announcer(
        speakers=StubRegistry(parlante=parlante, cocina=cocina),
        notify=lambda *_: None,
        fallback="parlante",
    )

    announcer.stop(["cocina"])
    announcer.stop([])

    assert cocina.stopped == 1
    assert parlante.stopped == 1, "sin equipos va al de siempre"


def test_a_device_that_cannot_stop_does_not_stop_the_others():
    broken = FakeSpeaker("cocina")
    broken.stop = lambda: (_ for _ in ()).throw(CastError("apagado"))
    parlante = FakeSpeaker("parlante")
    announcer = Announcer(
        speakers=StubRegistry(parlante=parlante, cocina=broken),
        notify=lambda *_: None,
        fallback="parlante",
    )

    announcer.stop(["cocina", "parlante"])

    assert parlante.stopped == 1


# --- modo vacaciones ---------------------------------------------------------


def test_on_vacation_the_alarm_is_only_written_with_its_buttons_and_the_reason(tmp_path):
    from homeauto.quiet import AwayStore, Hush, HushStore, QuietHours

    noon = datetime(2026, 10, 15, 12, 0)
    path = tmp_path / "jobs.db"
    hush = Hush(
        hours=QuietHours.parse("22:00", "05:25"),
        store=HushStore(path),
        clock=lambda: noon,
        away=AwayStore(path),
    )
    hush.start_away(datetime(2026, 10, 25, 0, 0))
    speaker = FakeSpeaker("parlante")
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda chat_id, text, actions=(): sent.append((chat_id, text, actions)),
        fallback="parlante",
        quiet=hush,
        clock=lambda: noon,
        actions=(("🔕 Apagar", "callar {job}"), ("Posponer 10 min", "posponer 10m")),
        ring_actions=(("🔕 Apagar", "callar {job}"),),
        chat_ids=(42, 99),
    )

    announcer(JOB)

    assert speaker.said == []
    assert [chat for chat, *_ in sent] == [42, 99]
    _, text, actions = sent[0]
    assert "De vacaciones hasta el 25/10: no lo dije en voz alta." in text
    assert actions == (("Posponer 10 min", "posponer 10m"),), "no repite: no hay nada que apagar"


def test_in_the_quiet_hours_the_alarm_keeps_its_off_button():
    announcer, _, sent = ringing(quiet=True)

    announcer(JOB)

    assert sent[0][2] == (("🔕 Apagar", "callar 7"), ("Posponer 10 min", "posponer 10m"))


# --- nombre entre corchetes ------------------------------------------------


class KeptPolish:
    def __init__(self):
        self.kept = []

    def __call__(self, text, must_keep=()):
        self.kept.append(tuple(must_keep))
        return text


def named(message):
    speaker = FakeSpeaker("parlante")
    sent = []
    polish = KeptPolish()
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda chat_id, text: sent.append(text),
        fallback="parlante",
        polish=polish,
    )
    announcer(Job(id=7, chat_id=42, when=JOB.when, message=message))
    return speaker, sent, polish


@pytest.mark.parametrize(
    "message, said",
    [
        ("[Papá] tomar medicación", "Papá, tomar medicación"),
        ("[Cin] Hora de levantarse.", "Cin, Hora de levantarse."),
        ("[Tía Ana]   regar", "Tía Ana, regar"),
    ],
)
def test_a_name_in_brackets_is_said_as_a_call(message, said):
    speaker, _, _ = named(message)

    assert speaker.said == [said]


def test_the_name_in_brackets_must_survive_the_polish():
    _, _, polish = named("[Papá] tomar medicación")

    assert polish.kept == [("Papá",)]


def test_the_chat_copy_says_the_same_as_the_speaker():
    _, sent, _ = named("[Papá] tomar medicación")

    assert "Papá, tomar medicación" in sent[0]
    assert "[Papá]" not in sent[0]


def test_the_name_in_brackets_lives_with_the_turn_prefix():
    speaker, _, polish = named("Le toca a Cin: [Papá] tomar medicación")

    assert speaker.said == ["Le toca a Cin: Papá, tomar medicación"]
    assert polish.kept == [("Cin", "Papá")]


@pytest.mark.parametrize(
    "message",
    [
        "tomar [la] pastilla",
        "[Papá2] tomar",
        "[] tomar",
        "[Papá tomar",
        " [Papá] tomar",
        "[Papá, Cin] tomar",
    ],
)
def test_any_other_bracket_stays_as_written(message):
    speaker, _, polish = named(message)

    assert speaker.said == [message]
    assert polish.kept == [()]


# --- la app de la tele ---------------------------------------------------------


@pytest.mark.parametrize("rest", ["quiet", "away"])
def test_in_the_quiet_hours_or_on_vacation_nothing_reaches_the_tele_app(tmp_path, rest):
    from homeauto.quiet import AwayStore, Hush, HushStore, QuietHours
    from homeauto.tele import TeleLink, TeleStore
    from homeauto.voice.speaker import Speaker
    from homeauto.voice.tele import TeleCaster

    at = datetime(2026, 10, 15, 23, 0) if rest == "quiet" else datetime(2026, 10, 15, 12, 0)
    path = tmp_path / "jobs.db"
    hush = Hush(
        hours=QuietHours.parse("22:00", "05:25"),
        store=HushStore(path),
        clock=lambda: at,
        away=AwayStore(path),
    )
    if rest == "away":
        hush.start_away(datetime(2026, 10, 25, 0, 0))
    link = TeleLink(TeleStore(path), clock=lambda: at)
    link.hello("comedor", "1.0", 1, ["play", "show"], "")
    cast = FakeSpeaker("comedor")
    speaker = Speaker(synth=None, caster=TeleCaster("comedor", cast, link), media_server=None)
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(comedor=speaker),
        notify=lambda chat_id, text, actions=(): sent.append(text),
        fallback="comedor",
        quiet=hush,
        clock=lambda: at,
    )

    announcer(JOB)

    assert link.orders("comedor") == []
    assert link.can("comedor", "play"), "la app estaba viva: no le llegó porque no se habló"
    assert len(sent) == 1


# --- asignación --------------------------------------------------------------


def addressed(message, addressee=None, audience=None, chat_ids=(42, 77)):
    speaker = FakeSpeaker("parlante")
    sent = []
    polish = KeptPolish()
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda chat_id, text: sent.append((chat_id, text)),
        fallback="parlante",
        polish=polish,
        chat_ids=chat_ids,
    )
    announcer(
        Job(
            id=7, chat_id=42, when=JOB.when, message=message,
            addressee=addressee, audience=audience,
        )
    )
    return speaker, sent, polish


@pytest.mark.parametrize(
    "addressee, said",
    [("China", "China, sacar la basura"), ("Todos", "Todos, sacar la basura")],
)
def test_the_assignment_is_said_as_a_call(addressee, said):
    speaker, sent, polish = addressed("sacar la basura", addressee)

    assert speaker.said == [said]
    assert polish.kept == [(addressee,)]
    assert said in sent[0][1]


def test_an_alarm_for_nobody_is_said_alone():
    speaker, _, polish = addressed("sacar la basura")

    assert speaker.said == ["sacar la basura"]
    assert polish.kept == [()]


def test_the_name_in_brackets_wins_over_the_assignment():
    speaker, _, polish = addressed("[Papá] tomar medicación", "China")

    assert speaker.said == ["Papá, tomar medicación"]
    assert polish.kept == [("Papá",)]


def test_the_turn_wins_over_the_assignment():
    speaker, _, polish = addressed("Le toca a Cin: sacar la basura", "China")

    assert speaker.said == ["Le toca a Cin: sacar la basura"]
    assert polish.kept == [("Cin",)]


def test_the_audience_of_the_job_decides_the_chats():
    _, sent, _ = addressed("sacar la basura", "China", audience=(77,))

    assert [chat for chat, _ in sent] == [77]


def test_without_an_audience_it_reaches_every_chat():
    _, sent, _ = addressed("sacar la basura", "Enano")

    assert sorted(chat for chat, _ in sent) == [42, 77]


def test_a_repetition_of_an_assigned_alarm_also_calls_by_name():
    speaker = FakeSpeaker("parlante")
    sent = []
    announcer = Announcer(
        speakers=StubRegistry(parlante=speaker),
        notify=lambda chat_id, text, actions=(): sent.append(chat_id),
        fallback="parlante",
        chat_ids=(42, 77),
    )

    announcer(
        Job(id=7, chat_id=42, when=JOB.when, message="arriba", addressee="China", audience=(77,)),
        rings=1,
    )

    assert speaker.said == ["China, arriba"]
    assert sent == [77]

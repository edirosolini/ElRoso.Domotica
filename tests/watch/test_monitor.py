from datetime import datetime, timedelta

from homeauto.watch.checks import Check, CheckResult, ProbeSkipped
from homeauto.watch.monitor import Monitor, down_line
from homeauto.watch.status import Status, StatusStore

NOW = datetime(2026, 8, 30, 10, 0)

LANDING = Check(name="landing", url="https://elroso.ar")
FACTURADOR = Check(name="facturador", url="https://facturador.elroso.ar", urgent=True)


def build(tmp_path, checks, answers, now=NOW, threshold=2):
    """`answers` mapea nombre -> lista de booleanos, una por vuelta."""
    said = []
    rounds = {name: list(values) for name, values in answers.items()}

    def runner(check, http, tcp, pause=0):
        up = rounds[check.name].pop(0)
        return CheckResult(check.name, up, "ok" if up else "HTTP 502", check.urgent, check.target)

    monitor = Monitor(
        checks=checks,
        store=StatusStore(tmp_path / "jobs.db"),
        announce=lambda text, urgent, detail="", check="": said.append((text, urgent, detail)),
        run=runner,
        clock=lambda: now,
        failures_to_declare=threshold,
    )
    return monitor, said


def test_a_healthy_service_says_nothing(tmp_path):
    monitor, said = build(tmp_path, [LANDING], {"landing": [True, True]})

    monitor.run_once()
    monitor.run_once()

    assert said == [], "un monitor que habla cuando todo anda es ruido"


def test_one_failure_is_not_an_outage(tmp_path):
    monitor, said = build(tmp_path, [LANDING], {"landing": [False]})

    monitor.run_once()

    assert said == [], "hay que aguantar antes de declarar una caída"


def test_two_failures_in_a_row_do_warn(tmp_path):
    monitor, said = build(tmp_path, [LANDING], {"landing": [False, False]})

    monitor.run_once()
    monitor.run_once()

    assert len(said) == 1
    assert "landing" in said[0][0]
    # El detalle viaja aparte: se escribe, no se dice.
    assert "502" not in said[0][0]
    assert "502" in said[0][2]


def test_the_spoken_alert_carries_no_digits(tmp_path):
    """Piper lee mal un dígito, y el detalle de la sonda está lleno de ellos."""
    monitor, said = build(tmp_path, [LANDING], {"landing": [False, False]})

    monitor.run_once()
    monitor.run_once()

    assert not any(char.isdigit() for char in said[0][0])


def test_the_alert_is_reworded_without_losing_the_name(tmp_path):
    monitor, said = build(tmp_path, [LANDING], {"landing": [False, False]})
    monitor.polish = lambda text, must_keep=(): f"[{must_keep[0]}] {text}"

    monitor.run_once()
    monitor.run_once()

    assert said[0][0].startswith("[landing]")


def test_it_does_not_repeat_while_it_stays_down(tmp_path):
    monitor, said = build(tmp_path, [LANDING], {"landing": [False] * 6})

    for _ in range(6):
        monitor.run_once()

    assert len(said) == 1, "avisa al caerse, no cada vuelta mientras dure"


def test_recovery_is_announced(tmp_path):
    monitor, said = build(tmp_path, [LANDING], {"landing": [False, False, True]})

    for _ in range(3):
        monitor.run_once()

    assert len(said) == 2
    assert "volvió" in said[1][0].lower() or "recuper" in said[1][0].lower()


def test_a_recovery_nobody_was_told_about_stays_quiet(tmp_path):
    """Una falla suelta que se arregla sola no merece dos mensajes."""
    monitor, said = build(tmp_path, [LANDING], {"landing": [False, True]})

    monitor.run_once()
    monitor.run_once()

    assert said == []


def test_the_alternation_does_not_spam(tmp_path):
    monitor, said = build(tmp_path, [LANDING], {"landing": [False, True, False, True]})

    for _ in range(4):
        monitor.run_once()

    assert said == []


def test_urgency_travels_with_the_alert(tmp_path):
    monitor, said = build(tmp_path, [FACTURADOR], {"facturador": [False, False]})

    monitor.run_once()
    monitor.run_once()

    assert said[0][1] is True


def test_a_recovery_is_never_urgent(tmp_path):
    monitor, said = build(tmp_path, [FACTURADOR], {"facturador": [False, False, True]})

    for _ in range(3):
        monitor.run_once()

    assert said[1][1] is False, "no hay que despertar a nadie por una buena noticia"


def test_several_services_are_independent(tmp_path):
    monitor, said = build(
        tmp_path,
        [LANDING, FACTURADOR],
        {"landing": [True, True], "facturador": [False, False]},
    )

    monitor.run_once()
    monitor.run_once()

    assert len(said) == 1 and "facturador" in said[0][0]


def test_the_state_survives_a_restart(tmp_path):
    monitor, said = build(tmp_path, [LANDING], {"landing": [False, False]})
    monitor.run_once()
    monitor.run_once()

    again, said_again = build(tmp_path, [LANDING], {"landing": [False, False]})
    again.run_once()
    again.run_once()

    assert len(said) == 1 and said_again == [], "reiniciar no puede re-anunciar lo mismo"


def test_it_reports_the_current_picture(tmp_path):
    monitor, _ = build(tmp_path, [LANDING, FACTURADOR], {"landing": [True], "facturador": [False]})

    monitor.run_once()
    picture = monitor.snapshot()

    assert picture["landing"].up is True
    assert picture["facturador"].up is False


# --- renombrar o sacar un chequeo no puede dejar un fantasma ----------------


def test_a_check_nobody_watches_anymore_is_not_reported(tmp_path):
    """🔴 Renombrar un chequeo dejaba la fila vieja en `/estado`, en rojo y para
    siempre: nadie la vuelve a chequear, así que nunca se recupera. Un monitor
    que muestra una caída que ya no existe enseña a no mirarlo."""
    store = StatusStore(tmp_path / "jobs.db")
    store.save(Status("vpn-vps", False, 9, True, "No route to host", NOW))
    store.save(Status("vps", True, 0, False, "conectó", NOW))

    monitor = Monitor(
        checks=[Check(name="vps", host="10.0.0.1", port=443)],
        store=store,
        announce=lambda *a, **k: None,
    )

    assert set(monitor.snapshot()) == {"vps"}


def test_what_is_configured_is_still_reported(tmp_path):
    store = StatusStore(tmp_path / "jobs.db")
    store.save(Status("vps", False, 2, True, "timeout", NOW))

    monitor = Monitor(
        checks=[Check(name="vps", host="10.0.0.1", port=443),
                Check(name="otro", host="10.0.0.2", port=443)],
        store=store,
        announce=lambda *a, **k: None,
    )

    assert set(monitor.snapshot()) == {"vps"}, "solo lo que ya tiene estado"


# --- confirmar la caída y re-avisar mientras nadie la confirme ----------------


class Watch:
    """Un monitor con reloj que se mueve y registro de todo lo que dijo."""

    def __init__(self, tmp_path, answers, checks=(LANDING,)):
        self.now = NOW
        self.said = []
        self.reminded = []
        self.others = []
        self.rounds = {name: list(values) for name, values in answers.items()}
        self.monitor = Monitor(
            checks=list(checks),
            store=StatusStore(tmp_path / "jobs.db"),
            announce=self.announce,
            remind=lambda text, name, detail="": self.reminded.append((self.now, text, name, detail)),
            tell_others=lambda chat_id, text: self.others.append((chat_id, text)),
            run=self.runner,
            clock=lambda: self.now,
        )

    def announce(self, text, urgent, detail="", check=""):
        self.said.append((text, urgent, detail, check))

    def runner(self, check, http, tcp, pause=0):
        values = self.rounds[check.name]
        up = values.pop(0) if len(values) > 1 else values[0]
        return CheckResult(check.name, up, "ok" if up else "HTTP 502", check.urgent, check.target)

    def minutes(self, count):
        """Corre una vuelta por minuto."""
        for _ in range(count):
            self.now += timedelta(minutes=1)
            self.monitor.run_once()


def declared(tmp_path, checks=(LANDING,), name="landing"):
    watch = Watch(tmp_path, {name: [False]}, checks)
    watch.monitor.run_once()
    watch.minutes(1)
    return watch, watch.now


def test_the_outage_names_its_check_so_it_can_be_confirmed(tmp_path):
    watch, _ = declared(tmp_path)

    assert watch.said[0][3] == "landing"


def test_the_recovery_offers_nothing_to_confirm(tmp_path):
    watch, _ = declared(tmp_path)
    watch.rounds["landing"] = [True]
    watch.minutes(1)

    assert "volvió" in watch.said[1][0]
    assert watch.said[1][3] == ""


def test_nobody_confirms_and_it_reminds_at_five_ten_fifteen_and_then_every_half_hour(tmp_path):
    watch, start = declared(tmp_path)

    watch.minutes(80)

    offsets = [int((at - start).total_seconds() // 60) for at, *_ in watch.reminded]
    assert offsets == [5, 10, 15, 45, 75]


def test_the_reminder_says_it_is_still_down_without_digits(tmp_path):
    watch, _ = declared(tmp_path)
    watch.monitor.polish = lambda text, must_keep=(): f"[{must_keep[0]}] {text}"

    watch.minutes(5)

    [(_, text, name, detail)] = watch.reminded
    assert text == "[landing] Atención: landing sigue sin responder."
    assert name == "landing"
    assert detail == "HTTP 502"
    assert not any(char.isdigit() for char in text)


def test_a_confirmed_outage_is_not_reminded(tmp_path):
    watch, _ = declared(tmp_path)

    reply = watch.monitor.acknowledge("landing", "Eze", 42)
    watch.minutes(80)

    assert "landing" in reply
    assert watch.reminded == []


def test_confirming_tells_the_other_alert_chats(tmp_path):
    watch, _ = declared(tmp_path)

    watch.monitor.acknowledge("landing", "Eze", 42)

    assert watch.others == [(42, "✅ Eze confirmó: landing no responde")]


def test_confirming_twice_says_it_already_was(tmp_path):
    watch, _ = declared(tmp_path)
    watch.monitor.acknowledge("landing", "Eze", 42)

    reply = watch.monitor.acknowledge("landing", "Ana", 77)

    assert "ya estaba confirmad" in reply
    assert len(watch.others) == 1


def test_confirming_after_the_recovery_says_it_came_back(tmp_path):
    watch, _ = declared(tmp_path)
    watch.rounds["landing"] = [True]
    watch.minutes(1)

    reply = watch.monitor.acknowledge("landing", "Eze", 42)

    assert reply == "landing ya volvió a responder."
    assert watch.others == []


def test_confirming_something_not_watched_says_so(tmp_path):
    watch, _ = declared(tmp_path)

    reply = watch.monitor.acknowledge("otro", "Eze", 42)

    assert "otro" in reply
    assert watch.others == []


def test_the_recovery_stops_the_reminders(tmp_path):
    watch, _ = declared(tmp_path)
    watch.minutes(5)
    watch.rounds["landing"] = [True]

    watch.minutes(60)

    assert len(watch.reminded) == 1


def test_a_new_outage_starts_unconfirmed_and_reminds_again(tmp_path):
    watch, _ = declared(tmp_path)
    watch.monitor.acknowledge("landing", "Eze", 42)
    watch.rounds["landing"] = [True]
    watch.minutes(1)
    watch.rounds["landing"] = [False]

    watch.minutes(2)
    watch.minutes(5)

    assert len(watch.said) == 3
    assert len(watch.reminded) == 1


def test_a_confirmation_while_the_alert_is_being_said_is_kept(tmp_path):
    """El botón llega con el aviso: el estado se guarda antes de hablar."""
    watch = Watch(tmp_path, {"landing": [False]})
    replies = []

    def announce(text, urgent, detail="", check=""):
        replies.append(watch.monitor.acknowledge(check, "Eze", 42))

    watch.monitor.announce = announce
    watch.monitor.run_once()
    watch.minutes(80)

    assert "landing" in replies[0] and "ya" not in replies[0]
    assert watch.reminded == []


def test_the_reminders_survive_a_restart(tmp_path):
    watch, _ = declared(tmp_path)
    watch.minutes(5)

    again = Watch(tmp_path, {"landing": [False]})
    again.now = watch.now
    again.minutes(5)

    assert len(watch.reminded) == 1 and len(again.reminded) == 1


def test_an_outage_alerted_before_the_reminders_existed_is_not_reminded(tmp_path):
    store = StatusStore(tmp_path / "jobs.db")
    store.save(Status("landing", False, 9, True, "HTTP 502", NOW))
    watch = Watch(tmp_path, {"landing": [False]})

    watch.minutes(80)

    assert watch.said == [] and watch.reminded == []


# --- sin internet en la ronda --------------------------------------------------


def offline_monitor(tmp_path, answers, online):
    """Un monitor que consulta `online[0]` antes de cada ronda."""
    said = []
    asked = []
    rounds = {name: list(values) for name, values in answers.items()}

    def runner(check, http, tcp, pause=0):
        asked.append(check.name)
        up = rounds[check.name].pop(0)
        return CheckResult(check.name, up, "ok" if up else "HTTP 502", check.urgent, check.target)

    monitor = Monitor(
        checks=[LANDING],
        store=StatusStore(tmp_path / "jobs.db"),
        announce=lambda text, urgent, detail="", check="": said.append(text),
        run=runner,
        clock=lambda: NOW,
        online=lambda: online[0],
    )
    return monitor, said, asked


def test_without_internet_the_round_counts_no_failures(tmp_path):
    online = [False]
    monitor, said, asked = offline_monitor(tmp_path, {"landing": [False, False]}, online)

    monitor.run_once()
    monitor.run_once()

    assert asked == [], "sin internet no se chequea nada"
    assert said == []
    assert monitor.store.get("landing") is None


def test_after_the_outage_the_vps_is_declared_only_after_two_rounds(tmp_path):
    online = [False]
    monitor, said, _ = offline_monitor(tmp_path, {"landing": [False, False]}, online)
    monitor.run_once()

    online[0] = True
    monitor.run_once()
    assert said == [], "la primera ronda con internet es la primera falla"

    monitor.run_once()
    assert len(said) == 1


def test_without_internet_a_declared_outage_is_not_reminded(tmp_path):
    watch, _ = declared(tmp_path)
    online = [False]
    watch.monitor.online = lambda: online[0]

    watch.minutes(30)

    assert watch.reminded == []


# --- la redacción de cada chequeo ---------------------------------------------

DISK = Check(
    name="el disco del proxmox",
    probe=lambda check: (True, ""),
    down="está casi lleno",
    up="volvió a tener lugar",
    still="sigue casi lleno",
    remind=False,
)
MACHINES = Check(
    name="las máquinas del proxmox",
    probe=lambda check: (True, ""),
    down="no están todas en marcha",
    up="volvieron a estar todas en marcha",
    still="siguen sin estar todas en marcha",
)


def test_the_existing_checks_keep_their_wording(tmp_path):
    watch, _ = declared(tmp_path)
    watch.minutes(5)
    reply = watch.monitor.acknowledge("landing", "Eze", 42)
    watch.rounds["landing"] = [True]
    watch.minutes(1)

    assert watch.said[0][0] == "Atención: landing no responde."
    assert watch.reminded[0][1] == "Atención: landing sigue sin responder."
    assert reply == "✅ Confirmado: landing no responde. No vuelvo a avisar hasta que vuelva."
    assert watch.others == [(42, "✅ Eze confirmó: landing no responde")]
    assert watch.said[1][0] == "landing volvió a responder."
    assert watch.monitor.acknowledge("landing", "Eze", 42) == "landing ya volvió a responder."


def test_a_check_says_its_own_wording(tmp_path):
    name = "las máquinas del proxmox"
    watch, _ = declared(tmp_path, checks=(MACHINES,), name=name)
    watch.minutes(5)
    reply = watch.monitor.acknowledge(name, "Eze", 42)
    watch.rounds[name] = [True]
    watch.minutes(1)

    assert watch.said[0][0] == f"Atención: {name} no están todas en marcha."
    assert watch.reminded[0][1] == f"Atención: {name} siguen sin estar todas en marcha."
    assert reply.startswith(f"✅ Confirmado: {name} no están todas en marcha.")
    assert watch.others == [(42, f"✅ Eze confirmó: {name} no están todas en marcha")]
    assert watch.said[1][0] == f"{name} volvieron a estar todas en marcha."
    assert watch.monitor.acknowledge(name, "Eze", 42) == (
        f"{name} ya volvieron a estar todas en marcha."
    )


def test_a_check_without_reminders_says_it_once(tmp_path):
    watch, _ = declared(tmp_path, checks=(DISK,), name="el disco del proxmox")

    watch.minutes(80)

    assert len(watch.said) == 1
    assert watch.reminded == []


def test_the_down_line_keeps_the_wording_of_a_service(tmp_path):
    monitor, _ = build(tmp_path, [LANDING], {"landing": [False]})
    monitor.run_once()

    assert down_line(monitor) == "Ojo: landing no responde."


def test_the_down_line_keeps_the_wording_of_several_services(tmp_path):
    monitor, _ = build(
        tmp_path, [LANDING, FACTURADOR], {"landing": [False], "facturador": [False]}
    )
    monitor.run_once()

    assert down_line(monitor) == "Ojo: no responden facturador ni landing."


def test_the_down_line_says_each_check_its_own_way(tmp_path):
    monitor, _ = build(
        tmp_path, [LANDING, DISK], {"landing": [False], "el disco del proxmox": [False]}
    )
    monitor.run_once()

    assert down_line(monitor) == "Ojo: landing no responde, y el disco del proxmox está casi lleno."


def test_the_down_line_only_about_a_check_with_its_wording(tmp_path):
    monitor, _ = build(tmp_path, [DISK], {"el disco del proxmox": [False]})
    monitor.run_once()

    assert down_line(monitor) == "Ojo: el disco del proxmox está casi lleno."


def test_the_down_line_without_the_checks_still_works():
    """El resumen recibe dobles que solo saben del estado."""

    class Bare:
        def snapshot(self):
            return {"landing": Status("landing", False, 2, True, "x", NOW)}

    assert down_line(Bare()) == "Ojo: landing no responde."


# --- una sonda que recuerda lo guardado ----------------------------------------


class RememberingProbe:
    def __init__(self):
        self.restored = []

    def restore(self, state):
        self.restored.append(state)

    def __call__(self, check):
        return True, "ok"


def test_a_probe_that_remembers_gets_the_saved_state_before_running(tmp_path):
    store = StatusStore(tmp_path / "jobs.db")
    saved = Status("disco", False, 2, True, "lleno", NOW)
    store.save(saved)
    remembering = RememberingProbe()
    monitor = Monitor(
        checks=[Check(name="disco", probe=remembering, attempts=1)],
        store=store,
        announce=lambda *a, **k: None,
        clock=lambda: NOW,
    )

    monitor.run_once()

    assert [state.up for state in remembering.restored] == [False]
    assert remembering.restored[0].detail == "lleno"


def test_a_probe_without_memory_is_left_alone(tmp_path):
    monitor, said = build(tmp_path, [LANDING], {"landing": [True]})

    monitor.run_once()

    assert said == []


# --- una sonda sin dato --------------------------------------------------------


def test_a_skipped_probe_moves_nothing(tmp_path):
    calls = []

    def runner(check, http, tcp, pause=0):
        calls.append(check.name)
        if len(calls) == 2:
            raise ProbeSkipped("la API no contestó")
        return CheckResult(check.name, False, "lleno", check.urgent, check.target)

    said = []
    monitor = Monitor(
        checks=[DISK],
        store=StatusStore(tmp_path / "jobs.db"),
        announce=lambda text, urgent, detail="", check="": said.append(text),
        run=runner,
        clock=lambda: NOW,
    )

    monitor.run_once()
    before = monitor.store.get("el disco del proxmox")
    monitor.run_once()
    after = monitor.store.get("el disco del proxmox")

    assert said == []
    assert before.failures == after.failures == 1

    monitor.run_once()
    assert len(said) == 1, "la vuelta salteada no cuenta, la siguiente sí"


def test_a_skipped_probe_on_a_declared_outage_neither_recovers_nor_reminds(tmp_path):
    watch, _ = declared(tmp_path)

    def skipped(check, http, tcp, pause=0):
        raise ProbeSkipped("sin datos")

    watch.monitor.run = skipped
    watch.minutes(20)

    assert len(watch.said) == 1
    assert watch.reminded == []
    assert watch.monitor.store.get("landing").up is False

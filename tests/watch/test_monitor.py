from datetime import datetime, timedelta

from homeauto.watch.checks import Check, CheckResult
from homeauto.watch.monitor import Monitor
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
        announce=lambda text, urgent, detail="": said.append((text, urgent, detail)),
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

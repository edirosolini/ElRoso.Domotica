import logging
from datetime import datetime

import pytest

from homeauto.watch.checks import ProbeSkipped, run_check
from homeauto.watch.loading import MAX_NAME_BYTES
from homeauto.watch.monitor import Monitor
from homeauto.watch.proxmox import (
    API_CHECK,
    BACKUPS_CHECK,
    DISK_CHECK,
    MACHINES_CHECK,
    ProxmoxClient,
    proxmox_checks,
)
from homeauto.watch.status import Status, StatusStore

URL = "https://192.0.2.10:8006"
# Inventado: la forma de un token de la API de Proxmox, no uno real.
TOKEN = "monitor@pve!casa=0b6f3a52-1c7e-4d2a-9e8b-5f4c3d2a1b0e"
SECRET = TOKEN.split("=", 1)[1]
GIB = 1024 ** 3

NODES = [{
    "node": "pve", "status": "online", "id": "node/pve", "type": "node", "level": "",
    "cpu": 0.02, "maxcpu": 4, "mem": 3 * GIB, "maxmem": 16 * GIB,
    "disk": 10 * GIB, "maxdisk": 100 * GIB, "uptime": 86400, "ssl_fingerprint": "AA:BB",
}]


def storage(name, used, total, active=1, enabled=1, kind="dir"):
    return {
        "storage": name, "type": kind, "content": "images,rootdir", "shared": 0,
        "active": active, "enabled": enabled, "total": total, "used": used,
        "avail": total - used, "used_fraction": used / total if total else 0,
    }


def status(used=20 * GIB, total=100 * GIB):
    return {
        "rootfs": {"total": total, "used": used, "avail": total - used, "free": total - used},
        "memory": {"total": 16 * GIB, "used": 3 * GIB, "free": 13 * GIB},
        "cpu": 0.02, "uptime": 86400, "loadavg": ["0.10", "0.20", "0.30"],
    }


def guest(vmid, name, state="running", kind="lxc", template=0):
    return {
        "id": f"{kind}/{vmid}", "type": kind, "vmid": vmid, "name": name, "node": "pve",
        "status": state, "template": template, "maxmem": GIB, "maxdisk": 8 * GIB, "uptime": 0,
    }


def task(state="OK", start=1_760_000_000, running=False):
    entry = {
        "upid": f"UPID:pve:0000ABCD:0001:{start:08X}:vzdump::root@pam:", "node": "pve",
        "pid": 43981, "pstart": 1, "starttime": start, "type": "vzdump", "id": "",
        "user": "root@pam",
    }
    if not running:
        entry["endtime"] = start + 600
        entry["status"] = state
    return entry


class FakeApi:
    """La API de Proxmox: contesta por ruta y registra cada pedido."""

    def __init__(self):
        self.routes = {
            "/nodes": (200, NODES),
            "/nodes/pve/storage": (200, [storage("local", 30 * GIB, 100 * GIB)]),
            "/nodes/pve/status": (200, status()),
            "/cluster/resources?type=vm": (200, [guest(300, "domotica")]),
            "/nodes/pve/tasks?typefilter=vzdump&limit=10": (200, [task()]),
        }
        self.calls = []
        self.boom = None

    def __call__(self, url, headers, verify, timeout):
        self.calls.append((url, dict(headers), verify))
        if self.boom:
            raise self.boom
        path = url.removeprefix(f"{URL}/api2/json")
        code, data = self.routes.get(path, (404, None))
        return code, ({"data": data} if data is not None else None)

    def paths(self):
        return [url.removeprefix(f"{URL}/api2/json") for url, _, _ in self.calls]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def build(api=None, clock=None, alert=85):
    api = api or FakeApi()
    clock = clock or Clock()
    client = ProxmoxClient(URL, TOKEN, ca_file="/etc/domotica/pve-ca.pem", fetch=api, clock=clock)
    checks = {check.name: check for check in proxmox_checks(client, disk_alert=alert)}
    return api, clock, client, checks


def probe(checks, name):
    return run_check(checks[name], http=None, tcp=None, pause=0)


# --- los cuatro chequeos ---------------------------------------------------------


def test_there_are_four_checks_none_urgent_and_one_attempt():
    _, _, _, checks = build()

    assert set(checks) == {API_CHECK, DISK_CHECK, MACHINES_CHECK, BACKUPS_CHECK}
    assert all(not check.urgent for check in checks.values())
    assert all(check.attempts == 1 for check in checks.values())


def test_only_the_stopped_machines_remind():
    _, _, _, checks = build()

    assert {name for name, check in checks.items() if check.remind} == {MACHINES_CHECK}


def test_the_names_fit_the_confirm_button_and_can_be_said():
    _, _, _, checks = build()

    for check in checks.values():
        assert len(check.name.encode()) <= MAX_NAME_BYTES
        assert not any(char.isdigit() or char == "-" for char in check.name)


def test_a_healthy_proxmox_is_up_everywhere():
    _, _, _, checks = build()

    assert all(probe(checks, name).up for name in checks)


# --- la API ----------------------------------------------------------------------


def test_the_token_goes_only_in_the_header():
    api, _, _, checks = build()

    probe(checks, API_CHECK)

    url, headers, verify = api.calls[0]
    assert headers == {"Authorization": f"PVEAPIToken={TOKEN}"}
    assert SECRET not in url
    assert verify == "/etc/domotica/pve-ca.pem"


def test_without_a_ca_it_verifies_against_the_system_and_never_turns_tls_off():
    api = FakeApi()
    client = ProxmoxClient(URL, TOKEN, fetch=api, clock=Clock())
    run_check(proxmox_checks(client)[0], http=None, tcp=None, pause=0)

    assert api.calls[0][2] is True


def test_a_rejected_token_is_the_api_down_and_the_rest_skipped():
    api = FakeApi()
    api.routes["/nodes"] = (401, None)
    _, _, _, checks = build(api)

    result = probe(checks, API_CHECK)

    assert result.up is False
    assert "401" in result.detail
    for name in (DISK_CHECK, MACHINES_CHECK, BACKUPS_CHECK):
        with pytest.raises(ProbeSkipped):
            probe(checks, name)


def test_an_unreachable_api_is_down_and_the_rest_skipped():
    api = FakeApi()
    api.boom = ConnectionError("Max retries exceeded with url: /api2/json/nodes")
    _, _, _, checks = build(api)

    assert probe(checks, API_CHECK).up is False
    with pytest.raises(ProbeSkipped):
        probe(checks, DISK_CHECK)


def test_one_pass_of_requests_per_round():
    api, clock, _, checks = build()

    for name in checks:
        probe(checks, name)
    first = list(api.paths())
    for name in checks:
        probe(checks, name)

    assert sorted(first) == sorted(set(first)), "cada ruta, una sola vez por vuelta"
    assert api.paths() == first, "la segunda vez sale del cache"

    clock.now += 120
    probe(checks, API_CHECK)
    assert len(api.paths()) == 2 * len(first)


def test_a_section_that_fails_skips_only_its_check():
    api = FakeApi()
    api.routes["/nodes/pve/storage"] = (500, None)
    _, _, _, checks = build(api)

    assert probe(checks, API_CHECK).up is True
    assert probe(checks, MACHINES_CHECK).up is True
    with pytest.raises(ProbeSkipped):
        probe(checks, DISK_CHECK)


# --- el disco ----------------------------------------------------------------------


def disk_at(api, percent):
    api.routes["/nodes/pve/storage"] = (200, [storage("local-lvm", percent * GIB, 100 * GIB, kind="lvmthin")])


def test_a_storage_over_the_threshold_is_down_with_its_name_in_the_detail():
    api = FakeApi()
    disk_at(api, 90)
    _, _, _, checks = build(api)

    result = probe(checks, DISK_CHECK)

    assert result.up is False
    assert "local-lvm" in result.detail and "90" in result.detail


def test_the_host_root_counts_too():
    api = FakeApi()
    api.routes["/nodes/pve/status"] = (200, status(used=88 * GIB))
    _, _, _, checks = build(api)

    result = probe(checks, DISK_CHECK)

    assert result.up is False
    assert "rootfs" in result.detail


def test_an_inactive_or_disabled_storage_does_not_count():
    api = FakeApi()
    api.routes["/nodes/pve/storage"] = (200, [
        storage("usb", 99 * GIB, 100 * GIB, active=0),
        storage("viejo", 99 * GIB, 100 * GIB, enabled=0),
        storage("local", 10 * GIB, 100 * GIB),
    ])
    _, _, _, checks = build(api)

    assert probe(checks, DISK_CHECK).up is True


def test_the_disk_comes_back_only_below_the_lower_mark():
    api = FakeApi()
    clock = Clock()
    _, _, _, checks = build(api, clock)
    seen = []
    for percent in (84, 86, 83, 81, 79, 84):
        disk_at(api, percent)
        clock.now += 120
        seen.append(probe(checks, DISK_CHECK).up)

    assert seen == [True, False, False, False, True, True]


def restarted_monitor(tmp_path, api, saved):
    """Un monitor recién arrancado sobre una base que ya guardaba el disco."""
    store = StatusStore(tmp_path / "jobs.db")
    if saved is not None:
        store.save(saved)
    clock = Clock()
    _, _, _, checks = build(api, clock)
    said = []
    monitor = Monitor(
        checks=[checks[DISK_CHECK]],
        store=store,
        announce=lambda text, urgent, detail="", check="": said.append(text),
        run=lambda check, http, tcp: run_check(check, http=http, tcp=tcp, pause=0),
    )
    return monitor, clock, said


def test_after_a_restart_a_disk_already_down_stays_down_between_the_marks(tmp_path):
    api = FakeApi()
    disk_at(api, 82)
    saved = Status(DISK_CHECK, False, 2, True, "local-lvm al 87%", datetime(2026, 10, 15, 9))
    monitor, clock, said = restarted_monitor(tmp_path, api, saved)

    monitor.run_once()

    assert said == [], "un ochenta y dos con la caída avisada no es que volvió"
    assert monitor.store.get(DISK_CHECK).up is False

    disk_at(api, 79)
    clock.now += 120
    monitor.run_once()
    assert said == [f"{DISK_CHECK} volvió a tener lugar."]


def test_after_a_restart_a_disk_that_was_up_is_up_between_the_marks(tmp_path):
    api = FakeApi()
    disk_at(api, 82)
    saved = Status(DISK_CHECK, True, 0, False, "local-lvm al 70%", datetime(2026, 10, 15, 9))
    monitor, _, said = restarted_monitor(tmp_path, api, saved)

    monitor.run_once()

    assert said == []
    assert monitor.store.get(DISK_CHECK).up is True


def test_the_saved_state_only_seeds_the_first_round():
    api = FakeApi()
    clock = Clock()
    _, _, _, checks = build(api, clock)
    disk = checks[DISK_CHECK]
    disk.probe.restore(Status(DISK_CHECK, False, 2, True, "", datetime(2026, 10, 15, 9)))
    disk_at(api, 82)
    assert probe(checks, DISK_CHECK).up is False

    disk.probe.restore(Status(DISK_CHECK, False, 2, True, "", datetime(2026, 10, 15, 9)))
    disk_at(api, 79)
    clock.now += 120
    assert probe(checks, DISK_CHECK).up is True
    disk_at(api, 82)
    clock.now += 120
    assert probe(checks, DISK_CHECK).up is True, "ya no vale lo guardado"


def test_the_threshold_comes_from_the_config():
    api = FakeApi()
    disk_at(api, 88)
    _, _, _, checks = build(api, alert=90)

    assert probe(checks, DISK_CHECK).up is True


# --- las máquinas ------------------------------------------------------------------


def test_a_stopped_machine_that_starts_on_boot_is_down():
    api = FakeApi()
    api.routes["/cluster/resources?type=vm"] = (200, [
        guest(300, "domotica"), guest(202, "vpn", state="stopped"),
    ])
    api.routes["/nodes/pve/lxc/202/config"] = (200, {"onboot": 1, "hostname": "vpn"})
    _, _, _, checks = build(api)

    result = probe(checks, MACHINES_CHECK)

    assert result.up is False
    assert "202" in result.detail and "vpn" in result.detail


def test_a_stopped_machine_without_onboot_is_fine():
    api = FakeApi()
    api.routes["/cluster/resources?type=vm"] = (200, [guest(105, "pruebas", state="stopped", kind="qemu")])
    api.routes["/nodes/pve/qemu/105/config"] = (200, {"name": "pruebas"})
    _, _, _, checks = build(api)

    assert probe(checks, MACHINES_CHECK).up is True


def test_a_template_is_never_a_stopped_machine():
    api = FakeApi()
    api.routes["/cluster/resources?type=vm"] = (200, [
        guest(9000, "debian", state="stopped", kind="qemu", template=1),
    ])
    _, _, _, checks = build(api)

    assert probe(checks, MACHINES_CHECK).up is True
    assert not any("9000" in path for path in api.paths()), "una plantilla no se consulta"


def test_running_machines_are_not_asked_for_their_config():
    api, _, _, checks = build()

    probe(checks, MACHINES_CHECK)

    assert not any(path.endswith("/config") for path in api.paths())


# --- los respaldos -----------------------------------------------------------------


def test_a_failed_backup_is_down_with_its_status_in_the_detail():
    api = FakeApi()
    api.routes["/nodes/pve/tasks?typefilter=vzdump&limit=10"] = (200, [
        task("job errors", start=2000), task("OK", start=1000),
    ])
    _, _, _, checks = build(api)

    result = probe(checks, BACKUPS_CHECK)

    assert result.up is False
    assert "job errors" in result.detail


def test_a_backup_with_warnings_is_not_down_but_says_so():
    api = FakeApi()
    api.routes["/nodes/pve/tasks?typefilter=vzdump&limit=10"] = (200, [task("WARNINGS: 2")])
    _, _, _, checks = build(api)

    result = probe(checks, BACKUPS_CHECK)

    assert result.up is True
    assert "WARNINGS: 2" in result.detail


def test_a_backup_in_progress_is_ignored():
    api = FakeApi()
    api.routes["/nodes/pve/tasks?typefilter=vzdump&limit=10"] = (200, [
        task(running=True, start=3000), task("job errors", start=2000),
    ])
    _, _, _, checks = build(api)

    assert probe(checks, BACKUPS_CHECK).up is False, "manda el último terminado"


def test_the_next_good_backup_brings_it_back():
    api = FakeApi()
    api.routes["/nodes/pve/tasks?typefilter=vzdump&limit=10"] = (200, [
        task("OK", start=3000), task("job errors", start=2000),
    ])
    _, _, _, checks = build(api)

    assert probe(checks, BACKUPS_CHECK).up is True


def test_without_any_finished_backup_there_is_nothing_to_say():
    api = FakeApi()
    api.routes["/nodes/pve/tasks?typefilter=vzdump&limit=10"] = (200, [task(running=True)])
    _, _, _, checks = build(api)

    with pytest.raises(ProbeSkipped):
        probe(checks, BACKUPS_CHECK)


# --- lo que se dice y lo que se escribe --------------------------------------------


def broken_api():
    api = FakeApi()
    disk_at(api, 95)
    api.routes["/cluster/resources?type=vm"] = (200, [guest(202, "vpn", state="stopped")])
    api.routes["/nodes/pve/lxc/202/config"] = (200, {"onboot": 1})
    api.routes["/nodes/pve/tasks?typefilter=vzdump&limit=10"] = (200, [task("job errors")])
    return api


def test_what_is_said_has_no_digits(tmp_path):
    api = broken_api()
    _, _, client, checks = build(api)
    said = []
    monitor = Monitor(
        checks=list(checks.values()),
        store=StatusStore(tmp_path / "jobs.db"),
        announce=lambda text, urgent, detail="", check="": said.append((text, detail)),
        run=lambda check, http, tcp: run_check(check, http=http, tcp=tcp, pause=0),
        failures_to_declare=1,
    )

    monitor.run_once()

    assert len(said) == 3
    for text, detail in said:
        assert not any(char.isdigit() for char in text), text
        assert detail


def test_the_secret_never_reaches_a_detail_or_the_log(caplog):
    api = FakeApi()
    api.boom = ConnectionError(f"fallo con {TOKEN} adentro")
    _, _, client, checks = build(api)

    with caplog.at_level(logging.DEBUG):
        details = [probe(checks, API_CHECK).detail]
        for name in (DISK_CHECK, MACHINES_CHECK, BACKUPS_CHECK):
            with pytest.raises(ProbeSkipped) as caught:
                probe(checks, name)
            details.append(str(caught.value))

    assert all(SECRET not in detail for detail in details)
    assert SECRET not in caplog.text
    assert SECRET not in repr(client)

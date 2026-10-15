"""La salud del Proxmox de casa por su API: que conteste, disco, máquinas y respaldos."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from homeauto.watch.checks import Check, ProbeSkipped

log = logging.getLogger(__name__)

# Se dicen en voz alta y viajan en el botón «Confirmar»: sin dígitos ni guiones.
API_CHECK = "proxmox"
DISK_CHECK = "el disco del proxmox"
MACHINES_CHECK = "las máquinas del proxmox"
BACKUPS_CHECK = "los respaldos"

DEFAULT_DISK_ALERT = 85
# El disco vuelve recién por debajo de la alerta menos esto.
DISK_HYSTERESIS = 5
# Menor que el intervalo mínimo del monitor: un pase por vuelta.
CACHE_SECONDS = 25
TIMEOUT = 10
TASKS_LIMIT = 10

Fetch = Callable[..., tuple[int, "dict | None"]]


def http_fetch(url: str, headers: dict, verify: str | bool, timeout: int) -> tuple[int, dict | None]:
    """GET a la API; devuelve el código y el JSON si fue un 200."""
    import requests

    response = requests.get(url, headers=headers, verify=verify, timeout=timeout)
    return response.status_code, response.json() if response.status_code == 200 else None


class _Failed(Exception):
    """Una ruta de la API no devolvió datos."""


@dataclass
class _Pass:
    """Lo leído en una vuelta: por ruta, el dato o el motivo por el que falta."""

    data: dict[str, object] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    nodes: list[str] = field(default_factory=list)

    def get(self, path: str):
        if path in self.errors:
            raise ProbeSkipped(f"{path}: {self.errors[path]}")
        return self.data[path]


class ProxmoxClient:
    """Lee la API del Proxmox una vez por vuelta y la comparte entre los chequeos."""

    def __init__(
        self,
        url: str,
        token: str,
        ca_file: str = "",
        fetch: Fetch = http_fetch,
        clock: Callable[[], float] = time.monotonic,
        cache_seconds: float = CACHE_SECONDS,
    ):
        self.url = url.rstrip("/")
        self._token = token
        self.verify: str | bool = ca_file or True
        self.fetch = fetch
        self.clock = clock
        self.cache_seconds = cache_seconds
        self._pass: _Pass | None = None
        self._at = 0.0

    def __repr__(self) -> str:
        return f"ProxmoxClient({self.url!r})"

    def current(self) -> _Pass:
        """El pase vigente; si venció, lee todo de nuevo."""
        now = self.clock()
        if self._pass is None or now - self._at >= self.cache_seconds:
            self._pass = self._read()
            self._at = now
        return self._pass

    def _scrub(self, text: str) -> str:
        """Saca el token de un texto que puede terminar en el chat o en el log."""
        secret = self._token.split("=", 1)[-1]
        return text.replace(self._token, "…").replace(secret, "…")

    def _get(self, path: str):
        try:
            code, body = self.fetch(
                f"{self.url}/api2/json{path}",
                {"Authorization": f"PVEAPIToken={self._token}"},
                self.verify,
                TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 - cualquier falla de red es "no hay dato"
            raise _Failed(self._scrub(f"{type(exc).__name__}: {exc}")) from None
        if code != 200 or not isinstance(body, dict) or "data" not in body:
            raise _Failed(f"HTTP {code}")
        return body["data"]

    def _read(self) -> _Pass:
        result = _Pass()
        try:
            nodes = self._get("/nodes")
        except _Failed as exc:
            log.warning("proxmox api failed: %s", exc)
            result.errors["/nodes"] = str(exc)
            return result
        result.data["/nodes"] = nodes
        result.nodes = sorted(n["node"] for n in nodes if n.get("status") == "online")

        paths = ["/cluster/resources?type=vm"]
        for node in result.nodes:
            paths += [
                f"/nodes/{node}/storage",
                f"/nodes/{node}/status",
                f"/nodes/{node}/tasks?typefilter=vzdump&limit={TASKS_LIMIT}",
            ]
        for path in paths:
            self._keep(result, path)

        guests = result.data.get("/cluster/resources?type=vm") or []
        for guest in _stopped(guests):
            self._keep(result, _config_path(guest))
        return result

    def _keep(self, result: _Pass, path: str) -> None:
        try:
            result.data[path] = self._get(path)
        except _Failed as exc:
            log.warning("proxmox %s failed: %s", path, exc)
            result.errors[path] = str(exc)

    def answered(self) -> _Pass:
        """El pase vigente, o `ProbeSkipped` si la API no contestó."""
        current = self.current()
        if "/nodes" in current.errors:
            raise ProbeSkipped(f"la API no contestó: {current.errors['/nodes']}")
        return current


def _stopped(guests: list[dict]) -> list[dict]:
    """Los guests parados que no son plantilla."""
    return [g for g in guests if not g.get("template") and g.get("status") != "running"]


def _config_path(guest: dict) -> str:
    return f"/nodes/{guest['node']}/{guest['type']}/{guest['vmid']}/config"


@dataclass
class ApiProbe:
    """Que la API conteste y acepte el token."""

    client: ProxmoxClient

    def __call__(self, check: Check) -> tuple[bool, str]:
        current = self.client.current()
        if "/nodes" in current.errors:
            return False, current.errors["/nodes"]
        return True, f"nodos en línea: {', '.join(current.nodes) or 'ninguno'}"


@dataclass
class DiskProbe:
    """Storages activos y la raíz del host por encima del umbral, con histéresis."""

    client: ProxmoxClient
    alert: int = DEFAULT_DISK_ALERT
    full: set[str] = field(default_factory=set)
    # Lo guardado como caído vale hasta la primera vuelta con datos.
    carried: bool = False
    restored: bool = False

    def restore(self, state) -> None:
        """Toma el último estado guardado, solo la primera vez."""
        if not self.restored:
            self.restored = True
            self.carried = state is not None and not state.up

    def __call__(self, check: Check) -> tuple[bool, str]:
        current = self.client.answered()
        usage: dict[str, float] = {}
        for node in current.nodes:
            for entry in current.get(f"/nodes/{node}/storage"):
                if entry.get("active") == 1 and entry.get("enabled", 1) == 1 and entry.get("total"):
                    usage[entry["storage"]] = entry["used"] / entry["total"] * 100
            rootfs = current.get(f"/nodes/{node}/status").get("rootfs") or {}
            if rootfs.get("total"):
                usage["rootfs"] = rootfs["used"] / rootfs["total"] * 100

        lower = self.alert - DISK_HYSTERESIS
        held = set(usage) if self.carried else self.full
        self.carried = False
        self.full = {
            name for name, percent in usage.items()
            if percent >= self.alert or (name in held and percent >= lower)
        }
        detail = ", ".join(
            f"{name} al {usage[name]:.0f}%"
            for name in sorted(usage, key=lambda name: (name not in self.full, name))
        )
        return not self.full, detail


@dataclass
class MachinesProbe:
    """Guests que arrancan con el host y están parados."""

    client: ProxmoxClient

    def __call__(self, check: Check) -> tuple[bool, str]:
        current = self.client.answered()
        guests = current.get("/cluster/resources?type=vm")
        down = [g for g in _stopped(guests) if current.get(_config_path(g)).get("onboot") == 1]
        if not down:
            return True, f"todas en marcha: {sum(1 for g in guests if not g.get('template'))}"
        down.sort(key=lambda g: g["vmid"])
        return False, "paradas: " + ", ".join(f"{g['vmid']} ({g.get('name', '?')})" for g in down)


@dataclass
class BackupProbe:
    """El último respaldo terminado: `OK` o `WARNINGS` está bien, lo demás es caída."""

    client: ProxmoxClient

    def __call__(self, check: Check) -> tuple[bool, str]:
        current = self.client.answered()
        finished = []
        for node in current.nodes:
            tasks = current.get(f"/nodes/{node}/tasks?typefilter=vzdump&limit={TASKS_LIMIT}")
            finished += [t for t in tasks if t.get("endtime") and t.get("status")]
        if not finished:
            raise ProbeSkipped("no hay respaldos terminados")
        last = max(finished, key=lambda t: t["endtime"])
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(last["endtime"]))
        state = last["status"]
        return state == "OK" or state.startswith("WARNINGS"), f"último respaldo {when}: {state}"


def proxmox_checks(client: ProxmoxClient, disk_alert: int = DEFAULT_DISK_ALERT) -> list[Check]:
    """Los cuatro chequeos del Proxmox, sobre un mismo cliente."""
    return [
        Check(name=API_CHECK, probe=ApiProbe(client), attempts=1, remind=False),
        Check(
            name=DISK_CHECK,
            probe=DiskProbe(client, disk_alert),
            attempts=1,
            down="está casi lleno",
            up="volvió a tener lugar",
            still="sigue casi lleno",
            remind=False,
        ),
        Check(
            name=MACHINES_CHECK,
            probe=MachinesProbe(client),
            attempts=1,
            down="no están todas en marcha",
            up="volvieron a estar todas en marcha",
            still="siguen sin estar todas en marcha",
        ),
        Check(
            name=BACKUPS_CHECK,
            probe=BackupProbe(client),
            attempts=1,
            down="fallaron",
            up="volvieron a salir bien",
            still="siguen fallando",
            remind=False,
        ),
    ]

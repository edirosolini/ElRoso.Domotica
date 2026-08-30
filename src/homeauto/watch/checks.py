"""Asking an external service whether it is still alive.

Deliberately small: an HTTP request or a TCP connection, with retries. A single
timeout is not an outage, and treating it as one is how a monitor teaches you
to ignore it.
"""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10
DEFAULT_ATTEMPTS = 2
RETRY_PAUSE = 2


@dataclass
class Check:
    name: str
    url: str = ""
    host: str = ""
    port: int = 0
    expect: int | None = None
    urgent: bool = False
    timeout: int = DEFAULT_TIMEOUT
    attempts: int = DEFAULT_ATTEMPTS

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("cada chequeo necesita un nombre")
        if not self.url and not (self.host and self.port):
            raise ValueError(f"'{self.name}': falta url, o host y port")

    @property
    def target(self) -> str:
        return self.url or f"{self.host}:{self.port}"


@dataclass(frozen=True)
class CheckResult:
    name: str
    up: bool
    detail: str
    urgent: bool = False
    target: str = ""
    extras: dict = field(default_factory=dict)


def http_request(url: str, timeout: int) -> tuple[int, float]:
    import requests

    started = time.monotonic()
    response = requests.get(url, timeout=timeout, allow_redirects=False)
    return response.status_code, time.monotonic() - started


def tcp_connect(host: str, port: int, timeout: int) -> float:
    started = time.monotonic()
    with socket.create_connection((host, port), timeout=timeout):
        return time.monotonic() - started


@dataclass
class HttpProbe:
    request: Callable[[str, int], tuple[int, float]] = http_request

    def __call__(self, check: Check) -> tuple[bool, str]:
        status, elapsed = self.request(check.url, check.timeout)
        if check.expect is not None:
            ok = status == check.expect
        else:
            ok = 200 <= status < 400
        return ok, f"HTTP {status} en {elapsed:.2f}s"


@dataclass
class TcpProbe:
    connect: Callable[[str, int, int], float] = tcp_connect

    def __call__(self, check: Check) -> tuple[bool, str]:
        elapsed = self.connect(check.host, check.port, check.timeout)
        return True, f"conectó en {elapsed:.2f}s"


def run_check(check: Check, http: HttpProbe | None, tcp: TcpProbe | None, pause: float = RETRY_PAUSE) -> CheckResult:
    probe = http if check.url else tcp
    if probe is None:
        return CheckResult(check.name, False, "no hay forma de chequearlo", check.urgent, check.target)

    problem = ""
    for attempt in range(1, max(1, check.attempts) + 1):
        try:
            ok, detail = probe(check)
            if ok:
                return CheckResult(check.name, True, detail, check.urgent, check.target)
            problem = detail
        except Exception as exc:  # noqa: BLE001 - cualquier fallo es "no responde"
            problem = f"{type(exc).__name__}: {exc}"

        # One timeout is not an outage; give it another go before saying so.
        if attempt < check.attempts and pause:
            time.sleep(pause)

    log.info("%s parece caído: %s", check.name, problem)
    return CheckResult(check.name, False, problem, check.urgent, check.target)

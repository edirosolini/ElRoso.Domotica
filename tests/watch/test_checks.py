import pytest

from homeauto.watch.checks import Check, CheckResult, HttpProbe, TcpProbe
from homeauto.watch.checks import run_check as _run_check


def run_check(check, http, tcp):
    # pause=0: los reintentos son lógica, no una excusa para dormir en los tests.
    return _run_check(check, http=http, tcp=tcp, pause=0)


class FakeHttp:
    def __init__(self, status=200, boom=None, elapsed=0.12):
        self.status = status
        self.boom = boom
        self.elapsed = elapsed
        self.calls = []

    def __call__(self, url, timeout):
        self.calls.append((url, timeout))
        if self.boom:
            raise self.boom
        return self.status, self.elapsed


class FakeTcp:
    def __init__(self, boom=None):
        self.boom = boom
        self.calls = []

    def __call__(self, host, port, timeout):
        self.calls.append((host, port, timeout))
        if self.boom:
            raise self.boom
        return 0.05


def test_a_healthy_http_service_is_up():
    check = Check(name="landing", url="https://elroso.ar")
    probe = HttpProbe(request=FakeHttp(status=200))

    result = run_check(check, http=probe, tcp=None)

    assert result.up is True
    assert result.name == "landing"
    assert result.detail


def test_an_unexpected_status_is_down():
    check = Check(name="landing", url="https://elroso.ar")
    probe = HttpProbe(request=FakeHttp(status=502))

    result = run_check(check, http=probe, tcp=None)

    assert result.up is False
    assert "502" in result.detail


def test_the_expected_status_can_be_something_else():
    check = Check(name="api", url="https://x/y", expect=401)
    probe = HttpProbe(request=FakeHttp(status=401))

    assert run_check(check, http=probe, tcp=None).up is True


def test_any_2xx_is_accepted_by_default():
    check = Check(name="landing", url="https://elroso.ar")

    for status in (200, 204, 301, 302):
        probe = HttpProbe(request=FakeHttp(status=status))
        assert run_check(check, http=probe, tcp=None).up is True, status


def test_a_network_error_is_down_with_the_reason():
    check = Check(name="landing", url="https://elroso.ar")
    probe = HttpProbe(request=FakeHttp(boom=TimeoutError("se agotó el tiempo")))

    result = run_check(check, http=probe, tcp=None)

    assert result.up is False
    assert "tiempo" in result.detail


def test_it_retries_before_giving_up():
    """Un timeout suelto no es una caída."""
    calls = []

    def flaky(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError("primera vez")
        return 200, 0.1

    check = Check(name="landing", url="https://elroso.ar", attempts=2)
    result = run_check(check, http=HttpProbe(request=flaky), tcp=None)

    assert result.up is True
    assert len(calls) == 2


def test_it_stops_retrying_once_it_works():
    probe = FakeHttp(status=200)
    check = Check(name="landing", url="https://elroso.ar", attempts=3)

    run_check(check, http=HttpProbe(request=probe), tcp=None)

    assert len(probe.calls) == 1


def test_a_tcp_port_that_answers_is_up():
    check = Check(name="vps-ssh", host="1.2.3.4", port=22)
    probe = TcpProbe(connect=FakeTcp())

    result = run_check(check, http=None, tcp=probe)

    assert result.up is True


def test_a_closed_port_is_down():
    check = Check(name="vps-ssh", host="1.2.3.4", port=22)
    probe = TcpProbe(connect=FakeTcp(boom=ConnectionRefusedError("cerrado")))

    result = run_check(check, http=None, tcp=probe).up

    assert result is False


def test_a_check_without_a_target_is_rejected():
    with pytest.raises(ValueError, match="url"):
        Check(name="vacio")


def test_a_check_needs_a_name():
    with pytest.raises(ValueError, match="nombre"):
        Check(name="", url="https://x")


def test_the_result_carries_the_urgency():
    check = Check(name="facturador", url="https://x", urgent=True)
    result = run_check(check, http=HttpProbe(request=FakeHttp(boom=OSError("caído"))), tcp=None)

    assert result.urgent is True
    assert isinstance(result, CheckResult)

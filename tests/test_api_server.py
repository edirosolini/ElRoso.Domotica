import json
import urllib.error
import urllib.request
from datetime import datetime

import pytest

from homeauto.api import ApiServer, ApiService
from homeauto.schedule.history import HistoryStore
from homeauto.schedule.store import Store
from homeauto.web.app import Response, WebApp
from homeauto.web.board import Board

from tests.conftest import FakeSpeaker, StubRegistry

TOKEN = "secreto-largo-de-verdad"


@pytest.fixture
def served():
    speaker = FakeSpeaker("parlante")
    service = ApiService(
        token=TOKEN,
        speakers=StubRegistry(parlante=speaker),
        default_devices=["parlante"],
        notify=lambda chat_id, text: None,
        chat_ids=(),
    )
    server = ApiServer(service, port=0, host="127.0.0.1")
    server.start()
    yield server, speaker
    server.stop()


def post(server, body, token=TOKEN, path="/say"):
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.actual_port}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read())


def test_a_post_makes_it_talk(served):
    server, speaker = served

    status, body = post(server, {"text": "backup terminado"})

    assert status == 200
    assert body["spoken"] is True
    assert speaker.said == ["backup terminado"]


def test_health_answers_without_a_token(served):
    server, _ = served

    with urllib.request.urlopen(f"http://127.0.0.1:{server.actual_port}/health", timeout=5) as r:
        assert json.loads(r.read())["ok"] is True


def test_a_wrong_token_gets_401(served):
    server, speaker = served

    with pytest.raises(urllib.error.HTTPError) as caught:
        post(server, {"text": "hola"}, token="cualquiera")

    assert caught.value.code == 401
    assert speaker.said == []


def test_no_token_gets_401(served):
    server, _ = served

    with pytest.raises(urllib.error.HTTPError) as caught:
        post(server, {"text": "hola"}, token="")

    assert caught.value.code == 401


def test_broken_json_gets_400(served):
    server, _ = served
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.actual_port}/say",
        data=b"{esto no es json",
        headers={"X-Token": TOKEN},
        method="POST",
    )

    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=5)

    assert caught.value.code == 400


def test_empty_text_gets_400(served):
    server, _ = served

    with pytest.raises(urllib.error.HTTPError) as caught:
        post(server, {"text": ""})

    assert caught.value.code == 400


def test_an_unknown_path_gets_404(served):
    server, _ = served

    with pytest.raises(urllib.error.HTTPError) as caught:
        post(server, {"text": "hola"}, path="/otra-cosa")

    assert caught.value.code == 404


def test_the_token_can_travel_in_the_body(served):
    """Para que un curl simple no necesite headers."""
    server, speaker = served

    status, _ = post(server, {"text": "hola", "token": TOKEN}, token="")

    assert status == 200
    assert speaker.said == ["hola"]


# --- la pantalla de la casa ---


class _Web:
    """Doble de WebApp: anota cada pedido y contesta como la de verdad."""

    def __init__(self):
        self.asked = []

    def handle(self, request):
        self.asked.append(request)
        return Response(
            status=200,
            body="<!doctype html><p>agenda ñandú</p>".encode("utf-8"),
            headers={"Content-Type": "text/html; charset=utf-8", "X-Prueba": "llego"},
        )

    __call__ = handle


def _service():
    return ApiService(
        token=TOKEN,
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        default_devices=["parlante"],
        notify=lambda chat_id, text: None,
        chat_ids=(),
    )


@pytest.fixture
def with_web():
    web = _Web()
    server = ApiServer(_service(), port=0, host="127.0.0.1", web=web)
    server.start()
    yield server, web
    server.stop()


def get(server, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{server.actual_port}{path}", timeout=5) as r:
        return r.status, r.headers, r.read().decode("utf-8")


def test_the_screen_answers_without_a_token(with_web):
    server, web = with_web

    status, headers, body = get(server, "/agenda")

    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert headers["X-Prueba"] == "llego"
    assert "agenda ñandú" in body
    assert [(r.method, r.path) for r in web.asked] == [("GET", "/agenda")]


def test_the_query_reaches_the_screen(with_web):
    server, web = with_web

    get(server, "/api/events?start=2026-10-05T00:00:00-03:00&end=2026-10-12")

    [request] = web.asked
    assert request.path == "/api/events"
    assert request.query == {"start": "2026-10-05T00:00:00-03:00", "end": "2026-10-12"}


def test_health_is_still_the_service_with_the_screen_on(with_web):
    server, web = with_web

    status, _, body = get(server, "/health")

    assert status == 200
    assert json.loads(body)["ok"] is True
    assert web.asked == []


def test_saying_still_needs_the_token_with_the_screen_on(with_web):
    server, web = with_web

    with pytest.raises(urllib.error.HTTPError) as caught:
        post(server, {"text": "hola"}, token="")

    assert caught.value.code == 401
    assert web.asked == []


def test_saying_still_works_with_the_screen_on(with_web):
    server, web = with_web

    status, _ = post(server, {"text": "hola"})

    assert status == 200
    assert web.asked == []


def test_a_post_elsewhere_goes_to_the_screen(with_web):
    server, web = with_web

    request = urllib.request.Request(
        f"http://127.0.0.1:{server.actual_port}/api/events", data=b"{}", method="POST"
    )
    urllib.request.urlopen(request, timeout=5).read()

    assert [(r.method, r.path) for r in web.asked] == [("POST", "/api/events")]


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_a_write_reaches_the_screen_with_its_headers_and_body(with_web, method):
    server, web = with_web
    host = f"127.0.0.1:{server.actual_port}"

    request = urllib.request.Request(
        f"http://{host}/api/jobs/7", data='{"message": "ñandú"}'.encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": f"http://{host}"},
        method=method,
    )
    urllib.request.urlopen(request, timeout=5).read()

    [asked] = web.asked
    assert (asked.method, asked.path) == (method, "/api/jobs/7")
    assert asked.body == '{"message": "ñandú"}'.encode("utf-8")
    assert asked.headers["content-type"] == "application/json"
    assert asked.headers["origin"] == f"http://{host}"
    assert asked.headers["host"] == host


def test_a_huge_write_to_the_screen_gets_413(with_web):
    server, web = with_web

    request = urllib.request.Request(
        f"http://127.0.0.1:{server.actual_port}/api/jobs", data=b"x" * (9 * 1024),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=5)

    assert caught.value.code == 413
    assert web.asked == []


def test_without_the_screen_the_agenda_does_not_exist(served):
    server, _ = served

    with pytest.raises(urllib.error.HTTPError) as caught:
        get(server, "/agenda")

    assert caught.value.code == 404


def test_the_real_screen_is_served_with_its_policy(tmp_path):
    board = Board(
        store=Store(tmp_path / "jobs.db"),
        history=HistoryStore(tmp_path / "jobs.db"),
        clock=lambda: datetime(2026, 10, 5, 12, 0),
    )
    server = ApiServer(_service(), port=0, host="127.0.0.1", web=WebApp(board))
    server.start()
    try:
        status, headers, body = get(server, "/api/events?start=2026-10-05&end=2026-10-12")
        assert status == 200
        assert json.loads(body) == {"events": [], "calendars": [], "problems": []}
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]

        with pytest.raises(urllib.error.HTTPError) as caught:
            get(server, "/api/events?start=2026-10-12&end=2026-10-05")
        assert caught.value.code == 400

        with pytest.raises(urllib.error.HTTPError) as caught:
            get(server, "/static/../web/app.py")
        assert caught.value.code == 404
    finally:
        server.stop()



import json
import urllib.error
import urllib.request

import pytest

from homeauto.api import ApiServer, ApiService

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


class _Page:
    """Doble de la página: anota el mes pedido y devuelve HTML."""

    def __init__(self):
        self.asked = []

    def html(self, month):
        self.asked.append(month)
        return "<!doctype html><p>agenda ñandú</p>"


@pytest.fixture
def with_page():
    page = _Page()
    service = ApiService(
        token=TOKEN,
        speakers=StubRegistry(parlante=FakeSpeaker("parlante")),
        default_devices=["parlante"],
        notify=lambda chat_id, text: None,
        chat_ids=(),
    )
    server = ApiServer(service, port=0, host="127.0.0.1", page=page)
    server.start()
    yield server, page
    server.stop()


def get(server, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{server.actual_port}{path}", timeout=5) as r:
        return r.status, r.headers.get("Content-Type"), r.read().decode("utf-8")


def test_the_month_page_answers_without_a_token(with_page):
    server, page = with_page

    status, content_type, body = get(server, "/agenda?m=2026-09")

    assert status == 200
    assert content_type.startswith("text/html")
    assert "agenda ñandú" in body
    assert page.asked == ["2026-09"]


def test_without_a_month_the_page_gets_none(with_page):
    server, page = with_page

    get(server, "/agenda")
    get(server, "/agenda/?m=cualquiera")

    assert page.asked == [None, "cualquiera"]


def test_saying_still_needs_the_token_with_the_page_on(with_page):
    server, _ = with_page

    with pytest.raises(urllib.error.HTTPError) as caught:
        post(server, {"text": "hola"}, token="")

    assert caught.value.code == 401


def test_without_a_page_the_agenda_does_not_exist(served):
    server, _ = served

    with pytest.raises(urllib.error.HTTPError) as caught:
        get(server, "/agenda")

    assert caught.value.code == 404

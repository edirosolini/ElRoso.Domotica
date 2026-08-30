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

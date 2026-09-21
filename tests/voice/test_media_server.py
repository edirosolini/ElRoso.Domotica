import urllib.request

import pytest

from homeauto.voice.media_server import MediaServer


@pytest.fixture
def served(tmp_path):
    (tmp_path / "hola.wav").write_bytes(b"RIFFfake")
    server = MediaServer(directory=tmp_path, advertised_ip="127.0.0.1", port=0)
    server.start()
    yield server, tmp_path
    server.stop()


def test_serves_a_file_from_the_directory(served):
    server, _ = served

    with urllib.request.urlopen(server.url_for("hola.wav"), timeout=5) as response:
        assert response.status == 200
        assert response.read() == b"RIFFfake"


def test_url_points_at_the_advertised_address(served):
    server, _ = served

    assert server.url_for("hola.wav") == f"http://127.0.0.1:{server.port}/hola.wav"


def test_unknown_file_is_a_404(served):
    server, _ = served

    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(server.url_for("no-esta.wav"), timeout=5)
    assert caught.value.code == 404


def test_cannot_escape_the_directory(served):
    server, _ = served

    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(f"http://127.0.0.1:{server.port}/../../etc/passwd", timeout=5)
    assert caught.value.code in (403, 404)


def test_two_speakers_starting_at_once_do_not_fight_for_the_port(tmp_path):
    """Sin candado los dos bindeaban y el segundo moría con «Address already in use»."""
    import threading

    server = MediaServer(tmp_path, advertised_ip="192.168.68.10", port=0)
    errors = []
    start = threading.Barrier(4)

    def run():
        start.wait()
        try:
            server.start()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    try:
        assert errors == []
        assert server.port != 0
    finally:
        server.stop()

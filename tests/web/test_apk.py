"""El estante de apps: solo lo de la lista, leído del disco en cada pedido."""

import pytest

from homeauto.web.apk import FILES, AppShelf


@pytest.fixture
def shelf(tmp_path):
    return AppShelf(tmp_path / "app")


def _put(shelf, name, data):
    shelf.directory.mkdir(parents=True, exist_ok=True)
    (shelf.directory / name).write_bytes(data)


def test_only_the_tv_app_and_its_version_are_on_the_list():
    assert FILES == ("tele.apk", "tele.json")


def test_the_version_comes_back_whole(shelf):
    _put(shelf, "tele.json", b'{"version_code": 3}')

    assert shelf.get("tele.json") == b'{"version_code": 3}'


@pytest.mark.parametrize("name", ["tele.apk", "tele.json"])
def test_without_any_file_there_is_nothing(shelf, name):
    assert shelf.get(name) is None


def test_the_tv_app_comes_back_whole(shelf):
    _put(shelf, "tele.apk", b"PK\x03\x04apk")

    assert shelf.get("tele.apk") == b"PK\x03\x04apk"


def test_without_the_file_there_is_nothing(shelf):
    assert shelf.get("tele.apk") is None


@pytest.mark.parametrize(
    "name", ["../jobs.db", "otro.apk", "", "tele.apk/..", "./tele.apk", "otro.json", "./tele.json"]
)
def test_a_name_off_the_list_does_not_touch_the_disk(shelf, name, tmp_path):
    _put(shelf, "tele.apk", b"apk")
    _put(shelf, "otro.apk", b"otro")
    (tmp_path / "jobs.db").write_bytes(b"secreto")

    assert shelf.get(name) is None


def test_a_replaced_app_is_seen_without_restarting(shelf):
    _put(shelf, "tele.apk", b"vieja")
    assert shelf.get("tele.apk") == b"vieja"

    _put(shelf, "tele.apk", b"nueva")

    assert shelf.get("tele.apk") == b"nueva"

import json

import pytest

from homeauto.watch.loading import ChecksError, load_checks


def write(tmp_path, payload):
    path = tmp_path / "checks.json"
    path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload, encoding="utf-8")
    return path


def test_a_missing_file_means_no_monitoring(tmp_path):
    assert load_checks(tmp_path / "no-existe.json") == []


def test_it_reads_the_services(tmp_path):
    path = write(tmp_path, [
        {"name": "landing", "url": "https://elroso.ar"},
        {"name": "vps", "host": "1.2.3.4", "port": 22, "urgent": True},
    ])

    checks = load_checks(path)

    assert [c.name for c in checks] == ["landing", "vps"]
    assert checks[1].port == 22
    assert checks[1].urgent is True


def test_defaults_are_filled_in(tmp_path):
    path = write(tmp_path, [{"name": "landing", "url": "https://elroso.ar"}])

    check = load_checks(path)[0]

    assert check.urgent is False
    assert check.timeout > 0
    assert check.attempts >= 1


def test_an_empty_list_is_fine(tmp_path):
    assert load_checks(write(tmp_path, [])) == []


def test_broken_json_is_reported_with_the_path(tmp_path):
    path = write(tmp_path, "{esto no es json")

    with pytest.raises(ChecksError, match="checks.json"):
        load_checks(path)


def test_something_that_is_not_a_list_is_rejected(tmp_path):
    with pytest.raises(ChecksError, match="lista"):
        load_checks(write(tmp_path, {"name": "landing"}))


def test_an_entry_without_a_target_names_itself(tmp_path):
    path = write(tmp_path, [{"name": "roto"}])

    with pytest.raises(ChecksError, match="roto"):
        load_checks(path)


def test_repeated_names_are_rejected(tmp_path):
    """El nombre es la clave del estado: repetirlo pisaría el del otro."""
    path = write(tmp_path, [
        {"name": "landing", "url": "https://a"},
        {"name": "landing", "url": "https://b"},
    ])

    with pytest.raises(ChecksError, match="repetido"):
        load_checks(path)


def test_an_unknown_field_is_rejected_instead_of_ignored(tmp_path):
    """Un typo silencioso en 'urgent' haría que nunca te despierte."""
    path = write(tmp_path, [{"name": "landing", "url": "https://a", "urgnet": True}])

    with pytest.raises(ChecksError, match="urgnet"):
        load_checks(path)

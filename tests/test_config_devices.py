import uuid

import pytest

from homeauto.config import Config, ConfigError

NEST = "d17e8311-d82e-5116-8f58-6292603bbc1b"
TV = "083e8ba4-67d7-e2d1-ac92-dcdd281d93bc"


def write_env(tmp_path, body):
    path = tmp_path / "domotica.env"
    path.write_text(body, encoding="utf-8")
    return path


def test_several_devices_with_aliases(tmp_path):
    path = write_env(tmp_path, f"""
TELEGRAM_TOKEN=123:ABC
CAST_DEVICES=parlante:{NEST}, tv:{TV}
CAST_DEFAULT=parlante
""")
    cfg = Config.from_file(path)

    assert cfg.devices == {"parlante": uuid.UUID(NEST), "tv": uuid.UUID(TV)}
    assert cfg.default_device == "parlante"
    assert cfg.cast_uuid == uuid.UUID(NEST), "cast_uuid sigue apuntando al de por defecto"


def test_first_device_is_the_default_when_not_said(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_DEVICES=parlante:{NEST}, tv:{TV}\n")
    cfg = Config.from_file(path)

    assert cfg.default_device == "parlante"


def test_aliases_are_case_insensitive(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_DEVICES=Parlante:{NEST}\nCAST_DEFAULT=PARLANTE\n")
    cfg = Config.from_file(path)

    assert "parlante" in cfg.devices
    assert cfg.default_device == "parlante"


def test_the_old_single_uuid_still_works(tmp_path):
    """La config vieja tenía un solo CAST_UUID: no debe romperse al desplegar."""
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={NEST}\n")
    cfg = Config.from_file(path)

    assert cfg.cast_uuid == uuid.UUID(NEST)
    assert list(cfg.devices) == ["parlante"]
    assert cfg.default_device == "parlante"


def test_devices_wins_over_the_old_key(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={NEST}\nCAST_DEVICES=tv:{TV}\n")
    cfg = Config.from_file(path)

    assert list(cfg.devices) == ["tv"]


def test_no_device_at_all_is_rejected(tmp_path):
    path = write_env(tmp_path, "TELEGRAM_TOKEN=123:ABC\n")
    with pytest.raises(ConfigError, match="CAST_DEVICES"):
        Config.from_file(path)


def test_malformed_entry_is_rejected(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_DEVICES={NEST}\n")
    with pytest.raises(ConfigError, match="alias:uuid"):
        Config.from_file(path)


def test_bad_uuid_names_the_alias(tmp_path):
    path = write_env(tmp_path, "TELEGRAM_TOKEN=123:ABC\nCAST_DEVICES=tv:no-es-uuid\n")
    with pytest.raises(ConfigError, match="tv"):
        Config.from_file(path)


def test_repeated_alias_is_rejected(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_DEVICES=tv:{NEST}, tv:{TV}\n")
    with pytest.raises(ConfigError, match="repetido"):
        Config.from_file(path)


def test_default_pointing_nowhere_is_rejected(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_DEVICES=parlante:{NEST}\nCAST_DEFAULT=cocina\n")
    with pytest.raises(ConfigError, match="CAST_DEFAULT"):
        Config.from_file(path)


def test_alias_with_spaces_is_rejected(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_DEVICES=el tv:{TV}\n")
    with pytest.raises(ConfigError, match="alias"):
        Config.from_file(path)


def test_knows_if_an_alias_exists(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_DEVICES=parlante:{NEST}\n")
    cfg = Config.from_file(path)

    assert cfg.has_device("parlante") is True
    assert cfg.has_device("PARLANTE") is True
    assert cfg.has_device("tv") is False

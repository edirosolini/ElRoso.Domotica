import uuid

import pytest

from homeauto.config import Config, ConfigError


def write_env(tmp_path, body):
    path = tmp_path / "nestbot.env"
    path.write_text(body, encoding="utf-8")
    return path


VALID_UUID = "d17e8311-d82e-5116-8f58-6292603bbc1b"


def test_loads_token_chat_ids_and_uuid(tmp_path):
    path = write_env(tmp_path, f"""
# comentario que se ignora

TELEGRAM_TOKEN=123:ABC
ALLOWED_CHAT_IDS=42, 77
CAST_UUID={VALID_UUID}
""")
    cfg = Config.from_file(path)

    assert cfg.telegram_token == "123:ABC"
    assert cfg.allowed_chat_ids == {42, 77}
    assert cfg.cast_uuid == uuid.UUID(VALID_UUID)


def test_empty_chat_ids_means_open_enrollment(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nALLOWED_CHAT_IDS=\nCAST_UUID={VALID_UUID}\n")
    cfg = Config.from_file(path)

    assert cfg.allowed_chat_ids == set()
    assert cfg.is_open_enrollment is True


def test_configured_chat_ids_close_enrollment(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nALLOWED_CHAT_IDS=42\nCAST_UUID={VALID_UUID}\n")
    cfg = Config.from_file(path)

    assert cfg.is_open_enrollment is False
    assert cfg.is_allowed(42) is True
    assert cfg.is_allowed(99) is False


def test_open_enrollment_allows_anyone(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\n")
    cfg = Config.from_file(path)

    assert cfg.is_allowed(12345) is True


def test_missing_token_is_rejected(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=\nCAST_UUID={VALID_UUID}\n")
    with pytest.raises(ConfigError, match="TELEGRAM_TOKEN"):
        Config.from_file(path)


def test_missing_uuid_is_rejected(tmp_path):
    path = write_env(tmp_path, "TELEGRAM_TOKEN=123:ABC\n")
    with pytest.raises(ConfigError, match="CAST_UUID"):
        Config.from_file(path)


def test_malformed_uuid_is_rejected(tmp_path):
    path = write_env(tmp_path, "TELEGRAM_TOKEN=123:ABC\nCAST_UUID=no-es-un-uuid\n")
    with pytest.raises(ConfigError, match="CAST_UUID"):
        Config.from_file(path)


def test_non_numeric_chat_id_is_rejected(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nALLOWED_CHAT_IDS=42,hola\nCAST_UUID={VALID_UUID}\n")
    with pytest.raises(ConfigError, match="ALLOWED_CHAT_IDS"):
        Config.from_file(path)


def test_surrounding_quotes_are_stripped(tmp_path):
    path = write_env(tmp_path, f'TELEGRAM_TOKEN="123:ABC"\nCAST_UUID={VALID_UUID}\n')
    cfg = Config.from_file(path)

    assert cfg.telegram_token == "123:ABC"


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="no existe"):
        Config.from_file(tmp_path / "no-esta.env")

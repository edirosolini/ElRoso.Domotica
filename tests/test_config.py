import uuid

import pytest

from homeauto.config import Config, ConfigError


def write_env(tmp_path, body):
    path = tmp_path / "domotica.env"
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


def test_missing_device_is_rejected(tmp_path):
    path = write_env(tmp_path, "TELEGRAM_TOKEN=123:ABC\n")
    with pytest.raises(ConfigError, match="CAST_DEVICES"):
        Config.from_file(path)


def test_malformed_uuid_is_rejected(tmp_path):
    path = write_env(tmp_path, "TELEGRAM_TOKEN=123:ABC\nCAST_UUID=no-es-un-uuid\n")
    with pytest.raises(ConfigError, match="CAST_UUID"):
        Config.from_file(path)


def test_missing_token_is_reported_before_the_devices(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=\nCAST_UUID={VALID_UUID}\n")
    with pytest.raises(ConfigError, match="TELEGRAM_TOKEN"):
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


# --- pulido de la redacción con un LLM ---

def test_without_a_key_the_polisher_is_off(tmp_path):
    """Apagado es el estado seguro: sin key, la casa habla igual que siempre."""
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\n")

    assert Config.from_file(path).polish_enabled is False


def test_a_key_turns_the_polisher_on(tmp_path):
    path = write_env(
        tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\nLLM_API_KEY=abc123\n"
    )
    cfg = Config.from_file(path)

    assert cfg.polish_enabled is True
    assert cfg.llm_api_key == "abc123"


def test_the_model_has_a_default(tmp_path):
    """Un modelo que razona antes de contestar tarda demasiado para un aviso."""
    path = write_env(
        tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\nLLM_API_KEY=k\n"
    )

    assert Config.from_file(path).llm_model
    assert "gemma" not in Config.from_file(path).llm_model


def test_the_model_can_be_changed(tmp_path):
    path = write_env(
        tmp_path,
        f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\nLLM_API_KEY=k\nLLM_MODEL=gemma-4-31b-it\n",
    )

    assert Config.from_file(path).llm_model == "gemma-4-31b-it"


def test_the_asking_model_is_not_the_polishing_one(tmp_path):
    """🔴 Medido contra la API real: el modelo del pulido buscó en 1 de 4 preguntas.

    Contestar de memoria una pregunta sobre hoy es peor que no contestar, así que
    el que pregunta tiene su propio default y no hereda el del pulido.
    """
    path = write_env(
        tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\nLLM_API_KEY=k\n"
    )
    cfg = Config.from_file(path)

    assert cfg.ask_model != cfg.llm_model
    assert "lite" not in cfg.ask_model, "los lite no usan la búsqueda de forma confiable"


def test_changing_the_polishing_model_does_not_drag_the_asking_one(tmp_path):
    path = write_env(
        tmp_path,
        f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\nLLM_API_KEY=k\nLLM_MODEL=uno\n",
    )
    cfg = Config.from_file(path)

    assert cfg.llm_model == "uno"
    assert cfg.ask_model != "uno"


def test_the_asking_model_can_be_changed_on_its_own(tmp_path):
    """Pulir una frase y contestar buscando no piden lo mismo de un modelo."""
    path = write_env(
        tmp_path,
        f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\n"
        "LLM_API_KEY=k\nLLM_MODEL=uno\nASK_MODEL=otro\n",
    )
    cfg = Config.from_file(path)

    assert cfg.llm_model == "uno"
    assert cfg.ask_model == "otro"

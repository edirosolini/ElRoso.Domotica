import uuid
from datetime import time

import pytest

from homeauto.config import Config, ConfigError
from tests.conftest import make_config


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


# --- el proveedor del texto: Google o Anthropic ---

BASE = f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\n"


def test_the_text_provider_is_google_by_default(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "LLM_API_KEY=k\n"))

    assert cfg.llm_provider == "google"
    assert cfg.text_model == cfg.llm_model
    assert cfg.text_ask_model == cfg.ask_model


def test_anthropic_reads_its_own_key_and_models(tmp_path):
    cfg = Config.from_file(
        write_env(tmp_path, BASE + "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\n")
    )

    assert cfg.llm_provider == "anthropic"
    assert cfg.anthropic_api_key == "sk-x"
    assert cfg.anthropic_model == "claude-haiku-5-5"
    assert cfg.anthropic_ask_model == "claude-sonnet-5-5"
    assert cfg.text_model == "claude-haiku-5-5"
    assert cfg.text_ask_model == "claude-sonnet-5-5"


def test_the_provider_name_ignores_case_and_spaces(tmp_path):
    cfg = Config.from_file(
        write_env(tmp_path, BASE + "LLM_PROVIDER= Anthropic \nANTHROPIC_API_KEY=sk-x\n")
    )

    assert cfg.llm_provider == "anthropic"


def test_the_anthropic_models_can_be_changed(tmp_path):
    cfg = Config.from_file(
        write_env(
            tmp_path,
            BASE + "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\n"
            "ANTHROPIC_MODEL=uno\nANTHROPIC_ASK_MODEL=otro\n",
        )
    )

    assert cfg.anthropic_model == "uno"
    assert cfg.anthropic_ask_model == "otro"


def test_changing_the_anthropic_model_does_not_drag_the_asking_one(tmp_path):
    """Haiku no busca en la web: el que pregunta no hereda el modelo barato."""
    cfg = Config.from_file(
        write_env(
            tmp_path,
            BASE + "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\nANTHROPIC_MODEL=uno\n",
        )
    )

    assert cfg.anthropic_ask_model == "claude-sonnet-5-5"


def test_anthropic_without_its_key_stops_the_service(tmp_path):
    path = write_env(tmp_path, BASE + "LLM_PROVIDER=anthropic\nLLM_API_KEY=k\n")

    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        Config.from_file(path)


def test_an_unknown_provider_stops_the_service(tmp_path):
    path = write_env(tmp_path, BASE + "LLM_PROVIDER=openai\n")

    with pytest.raises(ConfigError, match="LLM_PROVIDER"):
        Config.from_file(path)


def test_with_anthropic_the_text_is_on_without_a_google_key(tmp_path):
    """El texto depende de la clave de su proveedor; la transcripción, de la de Google."""
    cfg = Config.from_file(
        write_env(tmp_path, BASE + "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\n")
    )

    assert cfg.polish_enabled is True
    assert cfg.transcribe_enabled is False


def test_with_anthropic_and_a_google_key_voice_notes_are_still_heard(tmp_path):
    cfg = Config.from_file(
        write_env(
            tmp_path,
            BASE + "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\nLLM_API_KEY=k\n",
        )
    )

    assert cfg.polish_enabled is True
    assert cfg.transcribe_enabled is True


def test_with_google_an_anthropic_key_alone_does_not_turn_the_text_on(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "ANTHROPIC_API_KEY=sk-x\n"))

    assert cfg.polish_enabled is False
    assert cfg.transcribe_enabled is False


def test_the_anthropic_key_is_not_in_the_repr():
    cfg = make_config(llm_provider="anthropic", anthropic_api_key="sk-secreta")

    assert "sk-secreta" not in repr(cfg)


def test_a_config_built_in_code_uses_google():
    cfg = make_config()

    assert cfg.llm_provider == "google"
    assert cfg.polish_enabled is False
    assert cfg.transcribe_enabled is False


# --- el proveedor de las preguntas ---


def test_without_ask_provider_the_questions_follow_the_text(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "LLM_API_KEY=k\n"))

    assert cfg.ask_provider == "google"
    assert cfg.ask_enabled is True
    assert cfg.text_ask_model == cfg.ask_model


def test_an_empty_ask_provider_inherits_anthropic(tmp_path):
    cfg = Config.from_file(
        write_env(tmp_path, BASE + "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\nASK_PROVIDER=\n")
    )

    assert cfg.ask_provider == "anthropic"
    assert cfg.text_ask_model == "claude-sonnet-5-5"


def test_the_questions_can_go_to_anthropic_while_the_text_stays_on_google(tmp_path):
    cfg = Config.from_file(
        write_env(
            tmp_path,
            BASE + "LLM_API_KEY=k\nASK_PROVIDER= Anthropic \nANTHROPIC_API_KEY=sk-x\n",
        )
    )

    assert cfg.llm_provider == "google"
    assert cfg.text_model == cfg.llm_model
    assert cfg.ask_provider == "anthropic"
    assert cfg.ask_enabled is True
    assert cfg.text_ask_model == "claude-sonnet-5-5"


def test_the_questions_can_go_to_google_while_the_text_is_on_anthropic(tmp_path):
    cfg = Config.from_file(
        write_env(
            tmp_path,
            BASE + "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\n"
            "ASK_PROVIDER=google\nLLM_API_KEY=k\nASK_MODEL=caro\n",
        )
    )

    assert cfg.text_model == "claude-haiku-5-5"
    assert cfg.ask_provider == "google"
    assert cfg.ask_enabled is True
    assert cfg.text_ask_model == "caro"


def test_an_unknown_ask_provider_stops_the_service(tmp_path):
    path = write_env(tmp_path, BASE + "LLM_API_KEY=k\nASK_PROVIDER=openai\n")

    with pytest.raises(ConfigError, match="ASK_PROVIDER"):
        Config.from_file(path)


def test_asking_anthropic_without_its_key_stops_the_service(tmp_path):
    path = write_env(tmp_path, BASE + "LLM_API_KEY=k\nASK_PROVIDER=anthropic\n")

    with pytest.raises(ConfigError, match="ASK_PROVIDER=anthropic.*ANTHROPIC_API_KEY"):
        Config.from_file(path)


def test_asking_google_without_its_key_turns_only_the_questions_off(tmp_path):
    cfg = Config.from_file(
        write_env(
            tmp_path, BASE + "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-x\nASK_PROVIDER=google\n"
        )
    )

    assert cfg.polish_enabled is True
    assert cfg.ask_enabled is False


def test_a_config_built_in_code_asks_with_the_text_provider():
    cfg = make_config(llm_provider="anthropic", anthropic_api_key="sk-x")

    assert cfg.ask_provider == "anthropic"
    assert cfg.ask_enabled is True


# --- el resumen semanal ------------------------------------------------------


def test_the_weekly_summary_goes_out_on_sunday_evening_by_default(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\n"))

    assert cfg.weekly_at.days == (7,)
    assert cfg.weekly_at.at == time(19, 0)


def test_the_weekly_summary_can_be_turned_off(tmp_path):
    path = write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\nWEEKLY_AT=off\n")

    assert Config.from_file(path).weekly_at is None


def test_the_weekly_summary_takes_a_day_and_an_hour(tmp_path):
    path = write_env(
        tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\nWEEKLY_AT=lun 9:00\n"
    )
    cfg = Config.from_file(path)

    assert cfg.weekly_at.days == (1,)
    assert cfg.weekly_at.at == time(9, 0)


@pytest.mark.parametrize("raw", ["dom", "19:00", "xyz 19:00", "dom 25:00", "dom siete"])
def test_a_broken_weekly_summary_stops_the_service(tmp_path, raw):
    path = write_env(
        tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\nWEEKLY_AT={raw}\n"
    )

    with pytest.raises(ConfigError, match="WEEKLY_AT"):
        Config.from_file(path)


def test_a_config_built_in_code_has_no_weekly_summary():
    assert make_config().weekly_at is None


# --- Proxmox ------------------------------------------------------------------

# Inventado: la forma de un token de la API de Proxmox, no uno real.
PVE_TOKEN = "monitor@pve!casa=0b6f3a52-1c7e-4d2a-9e8b-5f4c3d2a1b0e"
PVE_SECRET = PVE_TOKEN.split("=", 1)[1]


def pve_env(tmp_path, extra):
    return write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\n{extra}")


def ca_file(tmp_path):
    path = tmp_path / "pve-ca.pem"
    path.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    return path


def test_without_a_pve_url_there_is_no_proxmox_watch(tmp_path):
    cfg = Config.from_file(pve_env(tmp_path, ""))

    assert cfg.pve_enabled is False


def test_a_config_built_in_code_has_no_proxmox():
    assert make_config().pve_enabled is False


def test_the_proxmox_pair_is_read(tmp_path):
    ca = ca_file(tmp_path)
    cfg = Config.from_file(pve_env(
        tmp_path, f"PVE_URL=https://192.0.2.10:8006/\nPVE_TOKEN={PVE_TOKEN}\nPVE_CA_FILE={ca}\n"
    ))

    assert cfg.pve_enabled is True
    assert cfg.pve_url == "https://192.0.2.10:8006"
    assert cfg.pve_token == PVE_TOKEN
    assert cfg.pve_ca_file == str(ca)
    assert cfg.pve_disk_alert == 85


def test_the_disk_threshold_can_be_moved(tmp_path):
    ca = ca_file(tmp_path)
    cfg = Config.from_file(pve_env(
        tmp_path,
        f"PVE_URL=https://pve:8006\nPVE_TOKEN={PVE_TOKEN}\nPVE_CA_FILE={ca}\nPVE_DISK_ALERT=90\n",
    ))

    assert cfg.pve_disk_alert == 90


@pytest.mark.parametrize("raw", ["0", "100", "noventa", "-5"])
def test_a_disk_threshold_out_of_range_stops_the_service(tmp_path, raw):
    ca = ca_file(tmp_path)
    path = pve_env(
        tmp_path,
        f"PVE_URL=https://pve:8006\nPVE_TOKEN={PVE_TOKEN}\nPVE_CA_FILE={ca}\nPVE_DISK_ALERT={raw}\n",
    )

    with pytest.raises(ConfigError, match="PVE_DISK_ALERT"):
        Config.from_file(path)


def test_a_url_without_a_token_stops_the_service(tmp_path):
    with pytest.raises(ConfigError, match="PVE_TOKEN"):
        Config.from_file(pve_env(tmp_path, "PVE_URL=https://pve:8006\n"))


def test_a_token_without_a_url_stops_the_service(tmp_path):
    with pytest.raises(ConfigError, match="PVE_URL"):
        Config.from_file(pve_env(tmp_path, f"PVE_TOKEN={PVE_TOKEN}\n"))


def test_the_proxmox_url_has_to_be_https(tmp_path):
    with pytest.raises(ConfigError, match="https"):
        Config.from_file(pve_env(tmp_path, f"PVE_URL=http://pve:8006\nPVE_TOKEN={PVE_TOKEN}\n"))


@pytest.mark.parametrize("raw", [
    "monitor@pve!casa",
    "monitor@pve=0b6f3a52-1c7e-4d2a-9e8b-5f4c3d2a1b0e",
    "monitor!casa=0b6f3a52-1c7e-4d2a-9e8b-5f4c3d2a1b0e",
    f"PVEAPIToken={PVE_TOKEN}",
    "monitor@pve!casa=no-es-un-secreto",
])
def test_a_malformed_token_stops_the_service_without_showing_it(tmp_path, raw):
    path = pve_env(tmp_path, f"PVE_URL=https://pve:8006\nPVE_TOKEN={raw}\n")

    with pytest.raises(ConfigError, match="PVE_TOKEN") as caught:
        Config.from_file(path)
    assert raw not in str(caught.value)
    assert PVE_SECRET not in str(caught.value)


def test_a_url_without_a_ca_file_stops_the_service(tmp_path):
    path = pve_env(tmp_path, f"PVE_URL=https://pve:8006\nPVE_TOKEN={PVE_TOKEN}\n")

    with pytest.raises(ConfigError, match="Falta PVE_CA_FILE"):
        Config.from_file(path)


def test_a_ca_file_that_does_not_exist_stops_the_service(tmp_path):
    path = pve_env(
        tmp_path,
        f"PVE_URL=https://pve:8006\nPVE_TOKEN={PVE_TOKEN}\nPVE_CA_FILE={tmp_path / 'no.pem'}\n",
    )

    with pytest.raises(ConfigError, match="PVE_CA_FILE"):
        Config.from_file(path)


def test_no_error_shows_the_proxmox_secret(tmp_path):
    for extra in (
        f"PVE_TOKEN={PVE_TOKEN}\n",
        f"PVE_URL=http://pve:8006\nPVE_TOKEN={PVE_TOKEN}\n",
        f"PVE_URL=https://pve:8006\nPVE_TOKEN={PVE_TOKEN}\nPVE_CA_FILE=/no/existe.pem\n",
        f"PVE_URL=https://pve:8006\nPVE_TOKEN={PVE_TOKEN}\nPVE_DISK_ALERT=200\n",
    ):
        with pytest.raises(ConfigError) as caught:
            Config.from_file(pve_env(tmp_path, extra))
        assert PVE_SECRET not in str(caught.value)


# --- la pantalla en la tele ---


def screen_env(tmp_path, extra=""):
    return write_env(tmp_path, f"TELEGRAM_TOKEN=123:ABC\nCAST_UUID={VALID_UUID}\n{extra}")


def test_the_screen_goes_to_the_dining_room_by_default(tmp_path):
    cfg = Config.from_file(screen_env(tmp_path))

    assert cfg.screen_device == "comedor"
    assert cfg.screen_devices == ("comedor", "recamara", "habitacion")


def test_the_screen_devices_are_read_from_the_env(tmp_path):
    cfg = Config.from_file(
        screen_env(tmp_path, "SCREEN_DEVICE=Recamara\nSCREEN_DEVICES=recamara, living\n")
    )

    assert cfg.screen_device == "recamara"
    assert cfg.screen_devices == ("recamara", "living")


def test_a_screen_alias_with_a_bad_shape_stops_the_service(tmp_path):
    with pytest.raises(ConfigError, match="SCREEN_DEVICES"):
        Config.from_file(screen_env(tmp_path, "SCREEN_DEVICES=comedor, la tele\n"))
    with pytest.raises(ConfigError, match="SCREEN_DEVICE"):
        Config.from_file(screen_env(tmp_path, "SCREEN_DEVICE=la tele\n"))


def test_a_config_built_in_code_has_the_screen_defaults():
    cfg = make_config()

    assert cfg.screen_device == "comedor"
    assert "parlante" not in cfg.screen_devices

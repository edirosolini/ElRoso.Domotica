"""Configuración de las instancias de Seq.

Cada VPS vigilado tiene su propio Seq: una clave por instancia, como los
calendarios. Una lista separada por comas sería ambigua — las URLs traen `:`
y `/` propios.
"""

import pytest

from homeauto.config import Config, ConfigError

NEST = "d17e8311-d82e-5116-8f58-6292603bbc1b"
BASE = f"TELEGRAM_TOKEN=123:ABC\nCAST_DEVICES=parlante:{NEST}\n"


def write_env(tmp_path, body):
    path = tmp_path / "domotica.env"
    path.write_text(body, encoding="utf-8")
    return path


def load(tmp_path, extra=""):
    return Config.from_file(write_env(tmp_path, BASE + extra))


# --- la forma vieja, de una sola instancia ---------------------------------

def test_seq_is_off_without_url_or_key(tmp_path):
    assert load(tmp_path).seq_enabled is False
    assert load(tmp_path, "SEQ_URL=http://172.68.0.7\n").seq_enabled is False
    assert load(tmp_path, "SEQ_API_KEY=abc\n").seq_enabled is False


def test_the_old_pair_still_works(tmp_path):
    """Hay bases desplegadas con SEQ_URL/SEQ_API_KEY sueltas."""
    cfg = load(tmp_path, "SEQ_URL=http://172.68.0.7\nSEQ_API_KEY=abc123\n")

    assert cfg.seq_enabled is True
    assert len(cfg.seq_instances) == 1
    assert cfg.seq_instances[0].url == "http://172.68.0.7"
    assert cfg.seq_instances[0].api_key == "abc123"
    assert cfg.seq_instances[0].alias == "", "la instancia de siempre no se renombra sola"


def test_a_seq_url_that_is_not_http_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="SEQ_URL"):
        load(tmp_path, "SEQ_URL=172.68.0.7\nSEQ_API_KEY=abc\n")


# --- una clave por instancia ----------------------------------------------

def test_an_aliased_instance_is_read(tmp_path):
    cfg = load(tmp_path, "SEQ_URL_HOSTING=http://172.68.1.7\nSEQ_API_KEY_HOSTING=abc123\n")

    assert cfg.seq_enabled is True
    assert len(cfg.seq_instances) == 1
    assert cfg.seq_instances[0].alias == "hosting"
    assert cfg.seq_instances[0].url == "http://172.68.1.7"
    assert cfg.seq_instances[0].api_key == "abc123"


def test_two_vps_are_two_instances(tmp_path):
    cfg = load(
        tmp_path,
        "SEQ_URL_HOSTING=http://172.68.1.7\nSEQ_API_KEY_HOSTING=una\n"
        "SEQ_URL_NUBE=http://172.68.2.7\nSEQ_API_KEY_NUBE=otra\n",
    )

    assert [i.alias for i in cfg.seq_instances] == ["hosting", "nube"]
    assert [i.api_key for i in cfg.seq_instances] == ["una", "otra"]


def test_the_old_pair_lives_alongside_an_aliased_one(tmp_path):
    cfg = load(
        tmp_path,
        "SEQ_URL=http://172.68.0.7\nSEQ_API_KEY=vieja\n"
        "SEQ_URL_HOSTING=http://172.68.1.7\nSEQ_API_KEY_HOSTING=nueva\n",
    )

    assert [i.alias for i in cfg.seq_instances] == ["", "hosting"]


def test_an_aliased_instance_without_its_key_stops_the_service(tmp_path):
    """🔴 Saltearla en silencio haría creer que se vigilan dos VPS y se vigila uno."""
    with pytest.raises(ConfigError, match="SEQ_API_KEY_HOSTING"):
        load(tmp_path, "SEQ_URL_HOSTING=http://172.68.1.7\n")


def test_an_aliased_url_that_is_not_http_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="SEQ_URL_HOSTING"):
        load(tmp_path, "SEQ_URL_HOSTING=172.68.1.7\nSEQ_API_KEY_HOSTING=abc\n")


def test_an_alias_with_digits_is_rejected(tmp_path):
    """🔴 El alias se dice en voz alta y Piper lee un dígito como cardinal suelto."""
    with pytest.raises(ConfigError, match="SEQ_URL_VPS2"):
        load(tmp_path, "SEQ_URL_VPS2=http://172.68.1.7\nSEQ_API_KEY_VPS2=abc\n")


def test_an_alias_with_a_dash_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="SEQ_URL_MI-VPS"):
        load(tmp_path, "SEQ_URL_MI-VPS=http://172.68.1.7\nSEQ_API_KEY_MI-VPS=abc\n")


def test_a_repeated_alias_is_impossible_by_construction(tmp_path):
    """Dos veces la misma clave: la última gana, como en cualquier archivo de entorno."""
    cfg = load(
        tmp_path,
        "SEQ_URL_HOSTING=http://uno\nSEQ_API_KEY_HOSTING=a\n"
        "SEQ_URL_HOSTING=http://dos\nSEQ_API_KEY_HOSTING=b\n",
    )

    assert len(cfg.seq_instances) == 1
    assert cfg.seq_instances[0].url == "http://dos"


# --- el enfriamiento es uno solo, compartido -------------------------------

def test_the_seq_cooldown_has_a_default(tmp_path):
    assert load(tmp_path).seq_cooldown > 0


def test_the_seq_cooldown_can_be_changed(tmp_path):
    assert load(tmp_path, "SEQ_COOLDOWN_MINUTES=30\n").seq_cooldown == 30


def test_an_aliased_key_without_its_url_stops_the_service(tmp_path):
    """El agujero simétrico: una clave suelta también es un VPS que se cree vigilado."""
    with pytest.raises(ConfigError, match="SEQ_URL_HOSTING"):
        load(tmp_path, "SEQ_API_KEY_HOSTING=abc\n")


def test_the_old_lone_url_stays_quiet(tmp_path):
    """🔴 El env desplegado tiene SEQ_URL con la clave vacía: no puede dejar de arrancar."""
    assert load(tmp_path, "SEQ_URL=http://172.68.0.7\nSEQ_API_KEY=\n").seq_enabled is False

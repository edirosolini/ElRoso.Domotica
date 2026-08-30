import pytest

from homeauto.config import Config, ConfigError

NEST = "d17e8311-d82e-5116-8f58-6292603bbc1b"
BASE = f"TELEGRAM_TOKEN=123:ABC\nCAST_DEVICES=parlante:{NEST}\n"


def write_env(tmp_path, body):
    path = tmp_path / "domotica.env"
    path.write_text(body, encoding="utf-8")
    return path


def test_coordinates_are_read(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "WEATHER_LAT=-31.42\nWEATHER_LON=-64.18\n"))

    assert cfg.weather_lat == pytest.approx(-31.42)
    assert cfg.weather_lon == pytest.approx(-64.18)


def test_there_is_a_default_so_it_works_out_of_the_box(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE))

    assert cfg.weather_lat is not None and cfg.weather_lon is not None


def test_the_place_name_is_optional(tmp_path):
    assert Config.from_file(write_env(tmp_path, BASE)).weather_place == ""
    cfg = Config.from_file(write_env(tmp_path, BASE + "WEATHER_PLACE=Córdoba\n"))
    assert cfg.weather_place == "Córdoba"


def test_a_coordinate_that_is_not_a_number_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="WEATHER_LAT"):
        Config.from_file(write_env(tmp_path, BASE + "WEATHER_LAT=por-alla\n"))


def test_a_coordinate_out_of_range_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="WEATHER_LAT"):
        Config.from_file(write_env(tmp_path, BASE + "WEATHER_LAT=120\n"))
    with pytest.raises(ConfigError, match="WEATHER_LON"):
        Config.from_file(write_env(tmp_path, BASE + "WEATHER_LON=-500\n"))


def test_quiet_hours_default_to_the_night(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE))

    assert cfg.quiet_hours.label == "23:00–07:00"
    assert cfg.quiet_hours.enabled is True


def test_quiet_hours_can_be_moved(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "QUIET_FROM=22:30\nQUIET_TO=08:00\n"))

    assert cfg.quiet_hours.label == "22:30–08:00"


def test_quiet_hours_can_be_turned_off(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "QUIET_FROM=00:00\nQUIET_TO=00:00\n"))

    assert cfg.quiet_hours.enabled is False


def test_a_broken_quiet_hour_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="QUIET"):
        Config.from_file(write_env(tmp_path, BASE + "QUIET_FROM=medianoche\n"))

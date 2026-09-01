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


def test_the_api_is_off_unless_a_token_is_set(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE))

    assert cfg.api_token == ""
    assert cfg.api_enabled is False


def test_a_token_turns_the_api_on(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "API_TOKEN=un-token-bien-largo-1234\n"))

    assert cfg.api_enabled is True
    assert cfg.api_port == 8099


def test_the_api_port_can_be_moved(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "API_TOKEN=un-token-bien-largo-1234\nAPI_PORT=9000\n"))

    assert cfg.api_port == 9000


def test_a_short_token_is_rejected(tmp_path):
    """Un token corto se adivina: mejor fallar al arrancar que quedar abierto."""
    with pytest.raises(ConfigError, match="API_TOKEN"):
        Config.from_file(write_env(tmp_path, BASE + "API_TOKEN=1234\n"))


def test_a_bad_port_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="API_PORT"):
        Config.from_file(write_env(tmp_path, BASE + "API_TOKEN=un-token-bien-largo-1234\nAPI_PORT=cero\n"))


def test_no_calendars_by_default(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE))

    assert cfg.calendars == {}
    assert cfg.calendar_enabled is False


def test_one_calendar_per_key(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + (
        "CALENDAR_URL_PERSONAL=https://calendar.google.com/calendar/ical/abc/basic.ics\n"
        "CALENDAR_URL_TRABAJO=https://calendar.google.com/calendar/ical/xyz/basic.ics\n"
    )))

    assert set(cfg.calendars) == {"personal", "trabajo"}
    assert cfg.calendars["personal"].endswith("abc/basic.ics")
    assert cfg.calendar_enabled is True


def test_a_single_unnamed_calendar_is_accepted(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "CALENDAR_URL=https://example.com/a.ics\n"))

    assert list(cfg.calendars) == ["agenda"]


def test_a_url_that_is_not_http_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="CALENDAR_URL_CASA"):
        Config.from_file(write_env(tmp_path, BASE + "CALENDAR_URL_CASA=file:///etc/passwd\n"))


def test_an_empty_calendar_url_is_ignored(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "CALENDAR_URL_PERSONAL=\n"))

    assert cfg.calendars == {}


def test_the_briefing_hour_has_a_default(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE))

    assert cfg.briefing_at is not None


def test_the_briefing_can_be_moved_or_turned_off(tmp_path):
    assert Config.from_file(write_env(tmp_path, BASE + "BRIEFING_AT=06:45\n")).briefing_at.strftime("%H:%M") == "06:45"
    assert Config.from_file(write_env(tmp_path, BASE + "BRIEFING_AT=off\n")).briefing_at is None


def test_the_event_warning_lead_time_has_a_default(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE))

    assert cfg.event_lead_minutes > 0


def test_the_lead_time_can_be_changed(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "EVENT_LEAD_MINUTES=20\n"))

    assert cfg.event_lead_minutes == 20


def test_the_checks_file_has_a_default_path(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE))

    assert str(cfg.checks_file).endswith("checks.json")


def test_the_checks_file_can_be_moved(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "CHECKS_FILE=/otro/lado/servicios.json\n"))

    assert str(cfg.checks_file) == "/otro/lado/servicios.json"


def test_the_check_interval_has_a_default(tmp_path):
    assert Config.from_file(write_env(tmp_path, BASE)).check_interval > 0


def test_the_check_interval_can_be_changed(tmp_path):
    cfg = Config.from_file(write_env(tmp_path, BASE + "CHECK_INTERVAL_SECONDS=300\n"))

    assert cfg.check_interval == 300


def test_a_too_small_interval_is_rejected(tmp_path):
    """Un intervalo de segundos machaca los servicios ajenos."""
    with pytest.raises(ConfigError, match="CHECK_INTERVAL_SECONDS"):
        Config.from_file(write_env(tmp_path, BASE + "CHECK_INTERVAL_SECONDS=5\n"))

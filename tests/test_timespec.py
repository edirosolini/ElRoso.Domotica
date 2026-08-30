from datetime import datetime

import pytest

from homeauto.timespec import TimeSpecError, parse_schedule

NOW = datetime(2026, 8, 29, 21, 0)  # sábado 21:00


def test_relative_minutes():
    when, message = parse_schedule("10m sacá la pizza", now=NOW)
    assert when == datetime(2026, 8, 29, 21, 10)
    assert message == "sacá la pizza"


def test_relative_accepts_spanish_abbreviations():
    assert parse_schedule("5min avisar", now=NOW)[0] == datetime(2026, 8, 29, 21, 5)
    assert parse_schedule("2h avisar", now=NOW)[0] == datetime(2026, 8, 29, 23, 0)
    assert parse_schedule("90s avisar", now=NOW)[0] == datetime(2026, 8, 29, 21, 1, 30)


def test_compound_relative_duration():
    when, _ = parse_schedule("1h30m avisar", now=NOW)
    assert when == datetime(2026, 8, 29, 22, 30)


def test_clock_time_later_today():
    when, message = parse_schedule("23:15 apagá el horno", now=NOW)
    assert when == datetime(2026, 8, 29, 23, 15)
    assert message == "apagá el horno"


def test_clock_time_already_passed_rolls_to_tomorrow():
    when, _ = parse_schedule("7:30 arriba", now=NOW)
    assert when == datetime(2026, 8, 30, 7, 30)


def test_explicit_tomorrow():
    when, message = parse_schedule("mañana 8:00 dentista", now=NOW)
    assert when == datetime(2026, 8, 30, 8, 0)
    assert message == "dentista"


def test_tomorrow_without_accent_is_accepted():
    when, _ = parse_schedule("manana 8:00 dentista", now=NOW)
    assert when == datetime(2026, 8, 30, 8, 0)


def test_message_keeps_internal_spacing_and_case():
    _, message = parse_schedule("10m  Sacá   la Pizza  ", now=NOW)
    assert message == "Sacá   la Pizza"


def test_zero_duration_is_rejected():
    with pytest.raises(TimeSpecError, match="mayor a cero"):
        parse_schedule("0m nada", now=NOW)


def test_missing_message_is_rejected():
    with pytest.raises(TimeSpecError, match="mensaje"):
        parse_schedule("10m", now=NOW)


def test_missing_message_after_clock_time_is_rejected():
    with pytest.raises(TimeSpecError, match="mensaje"):
        parse_schedule("7:30   ", now=NOW)


def test_unparseable_spec_is_rejected():
    with pytest.raises(TimeSpecError, match="No entiendo"):
        parse_schedule("cuando salga el sol avisame", now=NOW)


def test_invalid_clock_time_is_rejected():
    with pytest.raises(TimeSpecError, match="No entiendo"):
        parse_schedule("25:99 nada", now=NOW)


def test_empty_input_is_rejected():
    with pytest.raises(TimeSpecError):
        parse_schedule("   ", now=NOW)

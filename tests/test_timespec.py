from datetime import datetime

import pytest

from homeauto.timespec import (
    TimeSpecError,
    format_weekdays,
    next_weekday,
    parse_schedule,
    parse_weekdays,
)

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


# --- días de la semana -----------------------------------------------------


def test_weekday_range_expands_inclusive():
    assert parse_weekdays("lun-vie") == (1, 2, 3, 4, 5)


def test_weekday_range_wraps_around_the_weekend():
    assert parse_weekdays("vie-lun") == (1, 5, 6, 7)


def test_weekday_list_keeps_only_what_was_asked():
    assert parse_weekdays("lun,mie,vie") == (1, 3, 5)


def test_weekday_accepts_full_names_and_accents():
    assert parse_weekdays("miércoles,sábado") == (3, 6)


def test_weekday_is_case_insensitive():
    assert parse_weekdays("LUN-VIE") == (1, 2, 3, 4, 5)


def test_weekday_groups_have_a_shortcut():
    assert parse_weekdays("finde") == (6, 7)
    assert parse_weekdays("habiles") == (1, 2, 3, 4, 5)


def test_weekday_ranges_and_lists_combine():
    assert parse_weekdays("lun-mie,dom") == (1, 2, 3, 7)


def test_a_single_day_is_a_valid_spec():
    assert parse_weekdays("dom") == (7,)


def test_what_is_not_a_day_spec_is_not_one():
    assert parse_weekdays("7:30") is None
    assert parse_weekdays("diaria") is None
    assert parse_weekdays("lun-marte") is None
    assert parse_weekdays("") is None


def test_next_weekday_leaves_a_matching_day_alone():
    monday = datetime(2026, 8, 31, 5, 30)
    assert next_weekday(monday, (1, 2, 3, 4, 5)) == monday


def test_next_weekday_advances_to_the_first_match():
    sunday = datetime(2026, 8, 30, 5, 30)
    assert next_weekday(sunday, (1, 2, 3, 4, 5)) == datetime(2026, 8, 31, 5, 30)


def test_next_weekday_keeps_the_time_of_day():
    saturday = datetime(2026, 8, 29, 5, 30)
    assert next_weekday(saturday, (3,)) == datetime(2026, 9, 2, 5, 30)


def test_next_weekday_gives_up_on_days_that_match_nothing():
    with pytest.raises(TimeSpecError, match="días"):
        next_weekday(datetime(2026, 8, 30, 5, 30), ())


def test_weekdays_are_named_for_the_chat():
    assert format_weekdays((1, 2, 3, 4, 5)) == "lun, mar, mié, jue, vie"
    assert format_weekdays((6, 7)) == "sáb, dom"


def test_clock_time_accepts_a_dot_as_separator():
    when, message = parse_schedule("5.30 arriba", now=NOW)
    assert when == datetime(2026, 8, 30, 5, 30)
    assert message == "arriba"

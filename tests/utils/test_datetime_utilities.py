# tests/utils/test_datetime_utilities.py

import pendulum
import pytest

from src.utils.datetime_utilities import DateTimeUtility


@pytest.fixture(autouse=True)
def reset_cache():
    """
    Reset the cached current timestamp before each test.
    """
    DateTimeUtility._cached_now = None


def test_get_current_timestamp():
    """
    Test fetching the current timestamp with and without cache refresh.
    """
    now = DateTimeUtility.get_current_timestamp()
    assert isinstance(now, pendulum.DateTime)

    cached_now = DateTimeUtility.get_current_timestamp()
    assert now == cached_now

    refreshed_now = DateTimeUtility.get_current_timestamp(refresh=True)
    assert refreshed_now != now


def test_format_timestamp():
    """
    Test formatting timestamps.
    """
    timestamp = pendulum.datetime(2023, 1, 1, 12, 30, 45)
    formatted = DateTimeUtility.format_timestamp(timestamp)
    assert formatted == "2023-01-01 12:30:45"

    formatted_default = DateTimeUtility.format_timestamp()
    assert isinstance(formatted_default, str)


def test_parse_timestamp():
    """
    Test parsing timestamp strings.
    """
    timestamp_str = "2023-01-01 12:30:45"
    parsed = DateTimeUtility.parse_timestamp(timestamp_str)
    assert parsed == pendulum.datetime(2023, 1, 1, 12, 30, 45, tz="UTC")

    with pytest.raises(ValueError):
        DateTimeUtility.parse_timestamp("invalid-timestamp")


def test_to_iso8601():
    """
    Test converting timestamps to ISO 8601 format.
    """
    timestamp = pendulum.datetime(2023, 1, 1, 12, 30, 45)
    iso8601 = DateTimeUtility.to_iso8601(timestamp)
    assert iso8601 == "2023-01-01T12:30:45+00:00"

    iso8601_default = DateTimeUtility.to_iso8601()
    assert isinstance(iso8601_default, str)


def test_format_localized():
    """
    Test localized formatting of timestamps.
    """
    timestamp = pendulum.datetime(2023, 1, 1, 12, 30, 45)
    localized = DateTimeUtility.format_localized(timestamp, locale="en")
    assert localized.startswith("Sunday, January 1, 2023")

    with pytest.raises(ValueError):
        DateTimeUtility.format_localized(timestamp, locale="invalid-locale")


def test_calculate_elapsed_time():
    """
    Test calculating elapsed time between timestamps.
    """
    start_time = pendulum.datetime(2023, 1, 1, 12, 30, 45)
    end_time = pendulum.datetime(2023, 1, 1, 13, 30, 45)
    duration = DateTimeUtility.calculate_elapsed_time(start_time, end_time)
    assert duration.in_seconds() == 3600

    now = DateTimeUtility.get_current_timestamp()
    duration_from_now = DateTimeUtility.calculate_elapsed_time(start_time)
    assert duration_from_now.in_seconds() > 0


def test_add_time_delta():
    """
    Test adding time deltas to timestamps.
    """
    timestamp = pendulum.datetime(2023, 1, 1, 12, 30, 45)
    new_timestamp = DateTimeUtility.add_time_delta(timestamp, days=1, hours=2)
    assert new_timestamp == pendulum.datetime(2023, 1, 2, 14, 30, 45)


def test_register_custom_format():
    """
    Test registering and using custom formats.
    """
    DateTimeUtility.register_custom_format("custom1", "DD/MM/YYYY")
    assert "custom1" in DateTimeUtility.custom_formats

    formatted = DateTimeUtility.format_with_custom(
        pendulum.datetime(2023, 1, 1, 12, 30, 45), "custom1"
    )
    assert formatted == "01/01/2023"

    with pytest.raises(ValueError):
        DateTimeUtility.format_with_custom(
            pendulum.datetime(2023, 1, 1, 12, 30, 45), "nonexistent_format"
        )


def test_format_with_custom_default_timestamp():
    """
    Test using a custom format with the default current timestamp.
    """
    DateTimeUtility.register_custom_format("custom2", "YYYY-MM-DD")
    formatted = DateTimeUtility.format_with_custom(format_name="custom2")
    assert isinstance(formatted, str)

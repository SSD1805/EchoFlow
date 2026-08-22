import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scholion.media.time_coordinates import format_elapsed_timestamp


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "00:00:00.000"),
        (0.001, "00:00:00.001"),
        (59.999, "00:00:59.999"),
        (60.0, "00:01:00.000"),
        (3_600.0, "01:00:00.000"),
        (4_788.37, "01:19:48.370"),
        (86_400.0, "24:00:00.000"),
        (360_000.0, "100:00:00.000"),
        (59.9996, "00:01:00.000"),
    ],
)
def test_elapsed_timestamp_is_human_readable_unwrapped_and_rounds_safely(
    seconds, expected
):
    assert format_elapsed_timestamp(seconds) == expected


@pytest.mark.parametrize("seconds", [-0.001, math.inf, -math.inf, math.nan])
def test_elapsed_timestamp_rejects_noncanonical_coordinates(seconds):
    with pytest.raises(
        ValueError,
        match="^elapsed seconds must be finite and nonnegative$",
    ):
        format_elapsed_timestamp(seconds)


@given(st.integers(min_value=0, max_value=500 * 60 * 60 * 1_000))
def test_elapsed_timestamp_never_emits_sixty_for_minutes_or_seconds(total_ms):
    rendered = format_elapsed_timestamp(total_ms / 1_000)
    hours, minutes, rest = rendered.split(":")
    seconds, milliseconds = rest.split(".")

    assert int(hours) >= 0
    assert 0 <= int(minutes) < 60
    assert 0 <= int(seconds) < 60
    assert 0 <= int(milliseconds) < 1_000

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from omni_weather_forecast_apis.utils import localize_wall_time, resolve_wall_time


def test_localize_wall_time_uses_dst_rules() -> None:
    timezone = ZoneInfo("America/Los_Angeles")

    winter = localize_wall_time("2024-01-01T06:00:00", timezone)
    summer = localize_wall_time("2024-07-01T06:00:00", timezone)

    assert winter.astimezone(UTC) == datetime(2024, 1, 1, 14, tzinfo=UTC)
    assert summer.astimezone(UTC) == datetime(2024, 7, 1, 13, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("2024-03-10T02:30:00", "nonexistent local time"),
        ("2024-11-03T01:30:00", "ambiguous local time"),
    ],
)
def test_localize_wall_time_rejects_dst_discontinuities(
    value: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        localize_wall_time(value, ZoneInfo("America/Los_Angeles"))


def test_resolve_wall_time_matches_localize_for_normal_times() -> None:
    timezone = ZoneInfo("America/Los_Angeles")
    for value in ("2024-01-01T06:00:00", "2024-07-01T06:00:00"):
        assert resolve_wall_time(value, timezone) == localize_wall_time(
            value,
            timezone,
        )


def test_resolve_wall_time_fall_back_uses_earlier_occurrence() -> None:
    timezone = ZoneInfo("America/Los_Angeles")
    # 2024-11-03 01:30 occurs twice (clocks fall back). localize_wall_time
    # raises here; resolve_wall_time must pick the earlier (pre-transition,
    # PDT -07:00) instant instead of discarding the value.
    resolved = resolve_wall_time("2024-11-03T01:30:00", timezone)

    assert (resolved.year, resolved.month, resolved.day) == (2024, 11, 3)
    assert (resolved.hour, resolved.minute) == (1, 30)
    assert resolved.utcoffset() == timedelta(hours=-7)
    assert resolved.astimezone(UTC) == datetime(2024, 11, 3, 8, 30, tzinfo=UTC)


def test_resolve_wall_time_spring_forward_lands_on_real_instant() -> None:
    timezone = ZoneInfo("America/Los_Angeles")
    # 2024-03-10 02:30 never happens (clocks spring forward). resolve_wall_time
    # must return a real instant rather than raising.
    resolved = resolve_wall_time("2024-03-10T02:30:00", timezone)

    # It round-trips through UTC to a genuine wall time (03:30 PDT).
    assert resolved.astimezone(UTC).astimezone(timezone) == resolved
    assert resolved.astimezone(UTC) == datetime(2024, 3, 10, 10, 30, tzinfo=UTC)

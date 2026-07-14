from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from omni_weather_forecast_apis.utils import localize_wall_time


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

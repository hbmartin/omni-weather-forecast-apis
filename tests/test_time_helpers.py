from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from omni_weather_forecast_apis.utils import parse_date


def test_parse_date_preserves_timezone_aware_calendar_day() -> None:
    value = datetime(2026, 3, 12, 0, 30, tzinfo=timezone(timedelta(hours=1)))

    assert parse_date(value) == date(2026, 3, 12)


def test_parse_date_accepts_iso_datetime_strings() -> None:
    assert parse_date("2026-03-12T23:30:00-08:00") == date(2026, 3, 12)

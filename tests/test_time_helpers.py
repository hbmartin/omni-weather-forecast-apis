"""Tests for time helpers."""

from datetime import UTC, datetime

from omni_weather_forecast_apis.utils.time_helpers import (
    datetime_from_unix,
    parse_iso_datetime,
    unix_from_datetime,
)


class TestDatetimeFromUnix:
    def test_epoch(self):
        dt = datetime_from_unix(0)
        assert dt == datetime(1970, 1, 1, tzinfo=UTC)

    def test_known_timestamp(self):
        dt = datetime_from_unix(1704067200)
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1


class TestUnixFromDatetime:
    def test_epoch(self):
        dt = datetime(1970, 1, 1, tzinfo=UTC)
        assert unix_from_datetime(dt) == 0


class TestParseIsoDatetime:
    def test_with_timezone(self):
        dt = parse_iso_datetime("2024-01-01T00:00:00+00:00")
        assert dt.year == 2024
        assert dt.tzinfo is not None

    def test_without_timezone(self):
        dt = parse_iso_datetime("2024-01-01T00:00:00")
        assert dt.tzinfo == UTC

    def test_date_only(self):
        dt = parse_iso_datetime("2024-01-01")
        assert dt.year == 2024

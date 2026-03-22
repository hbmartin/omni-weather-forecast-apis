from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ForecastRequest,
    Granularity,
    MinutelyDataPoint,
    ProviderId,
    ProviderLogEvent,
    WeatherCondition,
    WeatherDataPoint,
)


def test_request_defaults_match_spec() -> None:
    request = ForecastRequest(latitude=34.0, longitude=-118.0)

    assert request.granularity == [Granularity.HOURLY, Granularity.DAILY]
    assert request.language == "en"
    assert request.include_raw is False


def test_data_points_are_frozen() -> None:
    point = WeatherDataPoint(
        timestamp=datetime(2026, 3, 12, 12, tzinfo=UTC),
        timestamp_unix=1,
        condition=WeatherCondition.CLEAR,
    )

    with pytest.raises(ValidationError):
        point.temperature = 25.0


def test_daily_point_supports_astronomy_fields() -> None:
    daily = DailyDataPoint(
        date=date(2026, 3, 12),
        sunrise=datetime(2026, 3, 12, 13, tzinfo=UTC),
        sunset=datetime(2026, 3, 12, 23, tzinfo=UTC),
        moon_phase=0.5,
    )

    assert daily.sunrise is not None
    assert daily.sunset is not None
    assert daily.moon_phase == 0.5


def test_minutely_point_shape() -> None:
    point = MinutelyDataPoint(
        timestamp=datetime(2026, 3, 12, 12, tzinfo=UTC),
        timestamp_unix=1710244800,
        precipitation_intensity=1.2,
        precipitation_probability=0.3,
    )

    assert point.precipitation_intensity == 1.2
    assert point.precipitation_probability == 0.3


def test_weather_data_point_normalizes_timestamps_to_utc() -> None:
    point = WeatherDataPoint(
        timestamp=datetime(2026, 3, 12, 12, tzinfo=timezone(timedelta(hours=-7))),
        timestamp_unix=1,
        condition=WeatherCondition.CLEAR,
    )

    assert point.timestamp == datetime(2026, 3, 12, 19, tzinfo=UTC)


def test_request_timeout_defaults_to_config_resolution() -> None:
    request = ForecastRequest(latitude=34.0, longitude=-118.0)

    assert request.timeout_ms is None


def test_provider_enum_contains_expected_slug() -> None:
    assert ProviderId.OPEN_METEO.value == "open_meteo"


def test_provider_log_event_defaults_timestamp_to_utc() -> None:
    before = datetime.now(UTC)
    event = ProviderLogEvent(
        provider=ProviderId.OPEN_METEO,
        phase="start",
        message="Fetching forecast",
    )
    after = datetime.now(UTC)

    assert before <= event.timestamp <= after
    assert event.timestamp.tzinfo == UTC

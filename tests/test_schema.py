from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import omni_weather_forecast_apis.types as public_types
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ForecastRequest,
    Granularity,
    HTTPConfig,
    MinutelyDataPoint,
    OmniWeatherConfig,
    ProviderId,
    ProviderLogEvent,
    RetryPolicy,
    WeatherCondition,
    WeatherDataPoint,
)


def test_request_defaults_match_spec() -> None:
    request = ForecastRequest(latitude=34.0, longitude=-118.0)

    assert request.granularity == [Granularity.HOURLY, Granularity.DAILY]
    assert request.language == "en"
    assert request.include_raw is False
    assert request.timezone is None


def test_request_accepts_only_loadable_iana_timezone_names() -> None:
    request = ForecastRequest(
        latitude=34.0,
        longitude=-118.0,
        timezone="America/Los_Angeles",
    )
    assert request.timezone == "America/Los_Angeles"

    with pytest.raises(ValidationError, match="loadable IANA name"):
        ForecastRequest(latitude=34.0, longitude=-118.0, timezone="UTC-08:00")


def test_config_defaults_match_request_defaults() -> None:
    config = OmniWeatherConfig(providers=[])

    assert config.granularity == [Granularity.HOURLY, Granularity.DAILY]
    assert config.language == "en"
    assert config.include_raw is False


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


def test_retry_policy_rejects_inverted_backoff_bounds() -> None:
    with pytest.raises(ValidationError, match="initial_backoff_ms"):
        RetryPolicy(initial_backoff_ms=2_000, max_backoff_ms=1_000)


def test_http_config_rejects_inverted_connection_bounds() -> None:
    with pytest.raises(ValidationError, match="max_keepalive_connections"):
        HTTPConfig(max_connections=2, max_keepalive_connections=3)


def test_retry_policy_clamps_unset_side_of_backoff_bounds() -> None:
    only_max = RetryPolicy(max_backoff_ms=400)
    assert only_max.initial_backoff_ms == 400

    only_initial = RetryPolicy(initial_backoff_ms=10_000)
    assert only_initial.max_backoff_ms == 10_000


def test_http_config_clamps_unset_side_of_connection_bounds() -> None:
    only_max = HTTPConfig(max_connections=5)
    assert only_max.max_keepalive_connections == 5

    only_keepalive = HTTPConfig(max_keepalive_connections=50)
    assert only_keepalive.max_connections == 50


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


def test_types_module_reexports_provider_configs() -> None:
    expected_names = {
        "GoogleWeatherConfig",
        "METNorwayConfig",
        "MetOfficeConfig",
        "MeteosourceConfig",
        "NWSConfig",
        "NWSGridOverride",
        "OpenMeteoConfig",
        "OpenWeatherConfig",
        "PirateWeatherConfig",
        "StormglassConfig",
        "TomorrowIOConfig",
        "VisualCrossingConfig",
        "WeatherAPIConfig",
        "WeatherbitConfig",
        "WeatherKitConfig",
        "XweatherConfig",
    }

    assert expected_names.issubset(public_types.__all__)
    assert all(hasattr(public_types, name) for name in expected_names)

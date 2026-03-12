"""Tests for common schema types."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from omni_weather_forecast_apis.types.schema import (
    AlertSeverity,
    DailyDataPoint,
    ErrorCode,
    ForecastRequest,
    ForecastResponse,
    ForecastResponseRequest,
    ForecastResponseSummary,
    Granularity,
    MinutelyDataPoint,
    ModelSource,
    ProviderError,
    ProviderErrorDetail,
    ProviderId,
    ProviderSuccess,
    SourceForecast,
    WeatherAlert,
    WeatherCondition,
    WeatherDataPoint,
)


class TestProviderId:
    def test_all_providers_exist(self):
        assert len(ProviderId) == 13

    def test_provider_values(self):
        assert ProviderId.OPENWEATHER.value == "openweather"
        assert ProviderId.OPEN_METEO.value == "open_meteo"
        assert ProviderId.NWS.value == "nws"
        assert ProviderId.STORMGLASS.value == "stormglass"


class TestModelSource:
    def test_creation(self):
        source = ModelSource(provider=ProviderId.OPENWEATHER, model="onecall_3.0")
        assert source.provider == ProviderId.OPENWEATHER
        assert source.model == "onecall_3.0"

    def test_frozen(self):
        source = ModelSource(provider=ProviderId.OPENWEATHER, model="test")
        with pytest.raises(ValidationError):
            source.provider = ProviderId.NWS  # type: ignore[misc]


class TestWeatherCondition:
    def test_all_conditions(self):
        assert len(WeatherCondition) == 26

    def test_condition_values(self):
        assert WeatherCondition.CLEAR.value == "clear"
        assert WeatherCondition.THUNDERSTORM_HEAVY.value == "thunderstorm_heavy"


class TestGranularity:
    def test_granularity_values(self):
        assert Granularity.MINUTELY.value == "minutely"
        assert Granularity.HOURLY.value == "hourly"
        assert Granularity.DAILY.value == "daily"


class TestWeatherDataPoint:
    def test_minimal(self):
        dp = WeatherDataPoint(
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            timestamp_unix=1704067200,
        )
        assert dp.temperature is None
        assert dp.wind_speed is None

    def test_full(self):
        dp = WeatherDataPoint(
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            timestamp_unix=1704067200,
            temperature=20.5,
            humidity=65.0,
            wind_speed=5.0,
            condition=WeatherCondition.CLEAR,
        )
        assert dp.temperature == 20.5
        assert dp.condition == WeatherCondition.CLEAR

    def test_precipitation_probability_bounds(self):
        dp = WeatherDataPoint(
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            timestamp_unix=1704067200,
            precipitation_probability=0.5,
        )
        assert dp.precipitation_probability == 0.5

        with pytest.raises(ValidationError):
            WeatherDataPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                timestamp_unix=1704067200,
                precipitation_probability=1.5,
            )


class TestMinutelyDataPoint:
    def test_creation(self):
        dp = MinutelyDataPoint(
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            timestamp_unix=1704067200,
            precipitation_intensity=0.5,
        )
        assert dp.precipitation_intensity == 0.5


class TestDailyDataPoint:
    def test_minimal(self):
        dp = DailyDataPoint(date=date(2024, 1, 1))
        assert dp.temperature_max is None
        assert dp.sunrise is None

    def test_full(self):
        dp = DailyDataPoint(
            date=date(2024, 1, 1),
            temperature_max=25.0,
            temperature_min=10.0,
            wind_speed_max=15.0,
            condition=WeatherCondition.PARTLY_CLOUDY,
            summary="Partly cloudy skies",
        )
        assert dp.temperature_max == 25.0
        assert dp.summary == "Partly cloudy skies"

    def test_moon_phase_bounds(self):
        dp = DailyDataPoint(date=date(2024, 1, 1), moon_phase=0.5)
        assert dp.moon_phase == 0.5

        with pytest.raises(ValidationError):
            DailyDataPoint(date=date(2024, 1, 1), moon_phase=1.5)


class TestWeatherAlert:
    def test_creation(self):
        alert = WeatherAlert(
            sender_name="NWS",
            event="Tornado Warning",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            description="Tornado warning for the area",
            severity=AlertSeverity.EXTREME,
        )
        assert alert.sender_name == "NWS"
        assert alert.severity == AlertSeverity.EXTREME


class TestSourceForecast:
    def test_empty_forecast(self):
        sf = SourceForecast(
            source=ModelSource(provider=ProviderId.OPENWEATHER, model="test")
        )
        assert sf.hourly == []
        assert sf.daily == []
        assert sf.minutely == []
        assert sf.alerts == []


class TestProviderResults:
    def test_success(self):
        result = ProviderSuccess(
            provider=ProviderId.OPENWEATHER,
            forecasts=[],
            fetched_at=datetime.now(UTC),
            latency_ms=150.0,
        )
        assert result.status == "success"

    def test_error(self):
        result = ProviderError(
            provider=ProviderId.OPENWEATHER,
            error=ProviderErrorDetail(
                code=ErrorCode.TIMEOUT,
                message="Request timed out",
                latency_ms=10000.0,
            ),
        )
        assert result.status == "error"
        assert result.error.code == ErrorCode.TIMEOUT


class TestForecastRequest:
    def test_defaults(self):
        req = ForecastRequest(latitude=34.0, longitude=-117.0)
        assert req.granularity == [Granularity.HOURLY, Granularity.DAILY]
        assert req.include_raw is False
        assert req.timeout_ms == 10_000

    def test_latitude_bounds(self):
        with pytest.raises(ValidationError):
            ForecastRequest(latitude=91.0, longitude=0.0)

    def test_longitude_bounds(self):
        with pytest.raises(ValidationError):
            ForecastRequest(latitude=0.0, longitude=181.0)


class TestForecastResponse:
    def test_creation(self):
        resp = ForecastResponse(
            request=ForecastResponseRequest(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            ),
            results=[],
            summary=ForecastResponseSummary(total=0, succeeded=0, failed=0),
            completed_at=datetime.now(UTC),
            total_latency_ms=0.0,
        )
        assert resp.summary.total == 0

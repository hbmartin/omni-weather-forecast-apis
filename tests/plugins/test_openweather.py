"""Tests for OpenWeather plugin using httpx2 mocks."""

from datetime import date

import httpx2
import pytest
import pytest_asyncio
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.openweather import (
    OpenWeatherConfig,
    openweather_plugin,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    PluginFetchParams,
    PluginFetchSuccess,
    PluginInstance,
    ProviderId,
)


class TestOpenWeatherPlugin:
    def test_plugin_id(self) -> None:
        assert openweather_plugin._id == ProviderId.OPENWEATHER

    def test_validate_config(self) -> None:
        config = openweather_plugin.validate_config({"api_key": "test-key"})
        assert isinstance(config, OpenWeatherConfig)
        assert config.api_key == "test-key"

    def test_validate_config_missing_key(self) -> None:
        with pytest.raises(ValidationError):
            openweather_plugin.validate_config({})


class TestOpenWeatherInstance:
    @pytest_asyncio.fixture
    async def instance(self) -> PluginInstance:
        config = openweather_plugin.validate_config({"api_key": "test-key"})
        return await openweather_plugin.initialize(config)

    def test_provider_id(self, instance: PluginInstance) -> None:
        assert instance.provider_id == ProviderId.OPENWEATHER

    def test_capabilities(self, instance: PluginInstance) -> None:
        caps = instance.get_capabilities()
        assert caps.granularity_minutely is True
        assert caps.granularity_hourly is True
        assert caps.granularity_daily is True
        assert caps.requires_api_key is True

    @pytest.mark.asyncio
    async def test_fetch_success(self, instance: PluginInstance) -> None:
        mock_response = {
            "timezone": "America/Los_Angeles",
            "hourly": [
                {
                    "dt": 1704067200,
                    "temp": 20.0,
                    "feels_like": 18.0,
                    "humidity": 65,
                    "wind_speed": 5.0,
                    "pressure": 1013,
                    "clouds": 50,
                    "weather": [{"id": 800, "description": "clear sky"}],
                },
            ],
            "daily": [
                {
                    "dt": 1704067200,
                    "temp": {"max": 25.0, "min": 10.0},
                    "humidity": 60,
                    "pressure": 1013,
                    "wind_speed": 10.0,
                    "clouds": 40,
                    "weather": [{"id": 801, "description": "few clouds"}],
                    "sunrise": 1704088800,
                    "sunset": 1704124800,
                },
            ],
        }

        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=mock_response),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY, Granularity.DAILY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts) == 1
        assert len(result.forecasts[0].hourly) == 1
        assert result.forecasts[0].hourly[0].temperature == 20.0
        assert len(result.forecasts[0].daily) == 1
        assert result.forecasts[0].daily[0].temperature_max == 25.0

    @pytest.mark.asyncio
    async def test_daily_dates_use_iana_timezone_and_alerts_have_no_url(
        self,
        instance: PluginInstance,
    ) -> None:
        # Daily dt 2023-12-31 22:00 UTC is 2024-01-01 00:00 at UTC+2; the
        # local calendar date must win over the UTC date.
        mock_response = {
            "timezone": "Europe/Athens",
            "daily": [
                {
                    "dt": 1704060000,
                    "temp": {"max": 5.0, "min": -1.0},
                },
            ],
            "alerts": [
                {
                    "sender_name": "Test Bureau",
                    "event": "Wind Advisory",
                    "start": 1704060000,
                    "end": 1704070000,
                    "description": "Windy.",
                    "tags": ["Extreme temperature value"],
                },
            ],
        }

        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=mock_response),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=52.0,
                longitude=21.0,
                granularity=[Granularity.DAILY],
                timezone="Pacific/Honolulu",
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        forecast = result.forecasts[0]
        assert forecast.timezone == "Europe/Athens"
        assert forecast.daily[0].date == date(2024, 1, 1)
        # One Call alert tags are category labels, never links.
        assert forecast.alerts[0].url is None

    @pytest.mark.asyncio
    async def test_fetch_auth_error(self, instance: PluginInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(401, json={"message": "unauthorized"}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            )
            result = await instance.fetch_forecast(params, client)

        assert result.status == "error"
        assert result.code == ErrorCode.AUTH_FAILED

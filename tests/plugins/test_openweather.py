"""Tests for OpenWeather plugin using httpx mocks."""

import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.openweather import openweather_plugin
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    OpenWeatherConfig,
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

        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, json=mock_response),
        )
        async with httpx.AsyncClient(transport=transport) as client:
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
    async def test_fetch_auth_error(self, instance: PluginInstance) -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(401, json={"message": "unauthorized"}),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            )
            result = await instance.fetch_forecast(params, client)

        assert result.status == "error"
        assert result.code == ErrorCode.AUTH_FAILED

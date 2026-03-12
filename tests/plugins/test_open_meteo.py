"""Tests for Open-Meteo plugin."""

import httpx
import pytest

from omni_weather_forecast_apis.plugins.open_meteo import (
    OpenMeteoConfig,
    OpenMeteoInstance,
    open_meteo_plugin,
)
from omni_weather_forecast_apis.types.plugin import PluginFetchParams, PluginFetchSuccess
from omni_weather_forecast_apis.types.schema import Granularity, ProviderId


class TestOpenMeteoPlugin:
    def test_plugin_id(self):
        assert open_meteo_plugin.id == ProviderId.OPEN_METEO

    def test_validate_config_defaults(self):
        config = open_meteo_plugin.validate_config({})
        assert isinstance(config, OpenMeteoConfig)
        assert config.api_key is None
        assert config.models == ["best_match"]


class TestOpenMeteoInstance:
    @pytest.fixture
    def instance(self):
        config = OpenMeteoConfig()
        return OpenMeteoInstance(config)

    def test_capabilities(self, instance):
        caps = instance.get_capabilities()
        assert caps.requires_api_key is False
        assert caps.multi_model is True

    @pytest.mark.asyncio
    async def test_fetch_success(self, instance):
        mock_response = {
            "hourly": {
                "time": ["2024-01-01T00:00", "2024-01-01T01:00"],
                "temperature_2m": [20.0, 19.5],
                "apparent_temperature": [18.0, 17.5],
                "weather_code": [0, 1],
                "is_day": [1, 0],
            },
            "daily": {
                "time": ["2024-01-01"],
                "temperature_2m_max": [25.0],
                "temperature_2m_min": [10.0],
                "weather_code": [0],
                "sunrise": ["2024-01-01T07:00"],
                "sunset": ["2024-01-01T17:00"],
            },
        }

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=mock_response)
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
        assert len(result.forecasts[0].hourly) == 2
        assert result.forecasts[0].hourly[0].temperature == 20.0
        assert len(result.forecasts[0].daily) == 1

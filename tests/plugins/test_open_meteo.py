"""Tests for Open-Meteo plugin using httpx mocks."""

import httpx
import pytest

from omni_weather_forecast_apis.plugins.open_meteo import (
    OpenMeteoInstance,
    open_meteo_plugin,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    OpenMeteoConfig,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
    ProviderId,
)


class TestOpenMeteoPlugin:
    def test_plugin_id(self) -> None:
        assert open_meteo_plugin._id == ProviderId.OPEN_METEO

    def test_validate_config_defaults(self) -> None:
        config = open_meteo_plugin.validate_config({})
        assert isinstance(config, OpenMeteoConfig)
        assert config.api_key is None
        assert config.models == ["best_match"]


class TestOpenMeteoInstance:
    @pytest.fixture
    def instance(self) -> OpenMeteoInstance:
        config = OpenMeteoConfig()
        return OpenMeteoInstance(config)

    def test_capabilities(self, instance: OpenMeteoInstance) -> None:
        caps = instance.get_capabilities()
        assert caps.requires_api_key is False
        assert caps.multi_model is True

    @pytest.mark.asyncio
    async def test_fetch_success(self, instance: OpenMeteoInstance) -> None:
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
        assert len(result.forecasts[0].hourly) == 2
        assert result.forecasts[0].hourly[0].temperature == 20.0
        assert len(result.forecasts[0].daily) == 1

    @pytest.mark.asyncio
    async def test_fetch_multi_model(self) -> None:
        """Multi-model responses use flat keys with model suffixes."""
        config = OpenMeteoConfig(models=["ecmwf_ifs025", "gfs_seamless"])
        instance = OpenMeteoInstance(config)

        mock_response = {
            "hourly_ecmwf_ifs025": {
                "time": ["2024-01-01T00:00"],
                "temperature_2m": [21.0],
                "weather_code": [0],
                "is_day": [1],
            },
            "hourly_gfs_seamless": {
                "time": ["2024-01-01T00:00"],
                "temperature_2m": [22.0],
                "weather_code": [1],
                "is_day": [1],
            },
        }

        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, json=mock_response),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts) == 2
        assert result.forecasts[0].source.model == "ecmwf_ifs025"
        assert result.forecasts[0].hourly[0].temperature == 21.0
        assert result.forecasts[1].source.model == "gfs_seamless"
        assert result.forecasts[1].hourly[0].temperature == 22.0

    @pytest.mark.asyncio
    async def test_fetch_http_error(self, instance: OpenMeteoInstance) -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(500, json={"error": "server error"}),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_fetch_empty_models_defaults_to_best_match(self) -> None:
        instance = OpenMeteoInstance(OpenMeteoConfig(models=[]))
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "hourly": {
                        "time": ["2024-01-01T00:00"],
                        "temperature_2m": [18.0],
                        "weather_code": [0],
                        "is_day": [1],
                    },
                },
            ),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                PluginFetchParams(
                    latitude=34.0,
                    longitude=-117.0,
                    granularity=[Granularity.HOURLY],
                ),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts) == 1
        assert result.forecasts[0].source.model == "best_match"
        assert result.forecasts[0].hourly[0].temperature == 18.0

    @pytest.mark.asyncio
    async def test_fetch_converts_units(self, instance: OpenMeteoInstance) -> None:
        captured_params: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_params["wind_speed_unit"] = request.url.params["wind_speed_unit"]
            return httpx.Response(
                200,
                json={
                    "minutely_15": {
                        "time": ["2024-01-01T00:00"],
                        "precipitation": [0.5],
                        "precipitation_probability": [25],
                    },
                    "hourly": {
                        "time": ["2024-01-01T00:00"],
                        "temperature_2m": [10.0],
                        "weather_code": [71],
                        "snowfall": [1.2],
                    },
                    "daily": {
                        "time": ["2024-01-01"],
                        "temperature_2m_max": [12.0],
                        "temperature_2m_min": [5.0],
                        "weather_code": [71],
                        "snowfall_sum": [2.3],
                    },
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[
                    Granularity.MINUTELY,
                    Granularity.HOURLY,
                    Granularity.DAILY,
                ],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        assert captured_params["wind_speed_unit"] == "ms"
        forecast = result.forecasts[0]
        assert forecast.minutely[0].precipitation_intensity == 2.0
        assert forecast.hourly[0].snow == 12.0
        assert forecast.daily[0].snowfall_sum == 23.0

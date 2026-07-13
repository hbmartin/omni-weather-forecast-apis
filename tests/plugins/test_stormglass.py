"""Tests for Stormglass plugin using httpx2 mocks."""

from __future__ import annotations

import httpx2
import pytest
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.stormglass import (
    StormglassConfig,
    StormglassInstance,
    _value_for_source,
    stormglass_plugin,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
    ProviderId,
)

DEFAULT_PARAMS = [
    "airTemperature",
    "humidity",
    "pressure",
    "windSpeed",
    "windDirection",
    "gust",
    "cloudCover",
    "precipitation",
    "visibility",
]


def _fetch_params() -> PluginFetchParams:
    return PluginFetchParams(
        latitude=34.0,
        longitude=-117.0,
        granularity=[Granularity.HOURLY],
    )


class TestValueForSource:
    def test_mapping_picks_source_key(self) -> None:
        assert _value_for_source({"sg": 1.5, "noaa": 2.0}, "sg") == 1.5
        assert _value_for_source({"sg": 1.5, "noaa": 2.0}, "noaa") == 2.0

    def test_plain_number_passes_through(self) -> None:
        assert _value_for_source(3.25, "sg") == 3.25

    def test_missing_source_returns_none(self) -> None:
        assert _value_for_source({"noaa": 2.0}, "sg") is None

    def test_none_returns_none(self) -> None:
        assert _value_for_source(None, "sg") is None


class TestStormglassPlugin:
    def test_plugin_id(self) -> None:
        assert stormglass_plugin.id == ProviderId.STORMGLASS

    def test_validate_config_defaults(self) -> None:
        config = stormglass_plugin.validate_config({"api_key": "test-key"})
        assert isinstance(config, StormglassConfig)
        assert config.api_key == "test-key"
        assert config.sources == ["sg"]
        assert config.params == DEFAULT_PARAMS

    def test_validate_config_missing_key(self) -> None:
        with pytest.raises(ValidationError):
            stormglass_plugin.validate_config({})

    def test_validate_config_empty_key(self) -> None:
        with pytest.raises(ValidationError):
            stormglass_plugin.validate_config({"api_key": ""})


class TestStormglassInstance:
    @pytest.fixture
    def instance(self) -> StormglassInstance:
        return StormglassInstance(StormglassConfig(api_key="test-key"))

    def test_provider_id(self, instance: StormglassInstance) -> None:
        assert instance.provider_id == ProviderId.STORMGLASS

    def test_capabilities_hourly_only(self, instance: StormglassInstance) -> None:
        caps = instance.get_capabilities()
        assert caps.granularity_minutely is False
        assert caps.granularity_hourly is True
        assert caps.granularity_daily is False
        assert caps.requires_api_key is True
        assert caps.multi_model is True

    @pytest.mark.asyncio
    async def test_fetch_success_multi_source(self) -> None:
        instance = StormglassInstance(
            StormglassConfig(api_key="test-key", sources=["sg", "noaa"]),
        )
        mock_response = {
            "hours": [
                {
                    "time": "2024-01-01T00:00:00+00:00",
                    "airTemperature": {"sg": 15.0, "noaa": 14.5},
                    "humidity": {"sg": 80.0, "noaa": 82.0},
                    "windSpeed": {"sg": 5.0, "noaa": 4.5},
                    "gust": {"sg": 8.0, "noaa": 7.5},
                    "windDirection": {"sg": 180.0, "noaa": 190.0},
                    "pressure": {"sg": 1013.0, "noaa": 1012.0},
                    "precipitation": {"sg": 0.1, "noaa": 0.2},
                    "cloudCover": {"sg": 75.0, "noaa": 70.0},
                    "visibility": {"sg": 10.0, "noaa": 9.0},
                },
            ],
            "meta": {"cost": 1},
        }

        captured_headers: dict[str, str] = {}
        captured_params: dict[str, str] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured_headers["authorization"] = request.headers["Authorization"]
            captured_params.update(dict(request.url.params))
            return httpx2.Response(200, json=mock_response)

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert captured_headers["authorization"] == "test-key"
        assert captured_params == {
            "lat": "34.0",
            "lng": "-117.0",
            "params": ",".join(DEFAULT_PARAMS),
            "source": "sg,noaa",
        }

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts) == 2
        sg_forecast, noaa_forecast = result.forecasts
        assert sg_forecast.source.provider == ProviderId.STORMGLASS
        assert sg_forecast.source.model == "sg"
        assert noaa_forecast.source.model == "noaa"

        assert len(sg_forecast.hourly) == 1
        sg_point = sg_forecast.hourly[0]
        assert sg_point.temperature == 15.0
        assert sg_point.humidity == 80.0
        assert sg_point.wind_speed == 5.0
        assert sg_point.wind_gust == 8.0
        assert sg_point.wind_direction == 180.0
        assert sg_point.pressure_sea == 1013.0
        assert sg_point.precipitation == 0.1
        assert sg_point.cloud_cover == 75.0
        assert sg_point.visibility == 10.0

        noaa_point = noaa_forecast.hourly[0]
        assert noaa_point.temperature == 14.5
        assert noaa_point.wind_direction == 190.0
        assert noaa_point.precipitation == 0.2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [401, 403])
    async def test_fetch_auth_error(
        self,
        instance: StormglassInstance,
        status_code: int,
    ) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(
                status_code,
                json={"message": "unauthorized"},
            ),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.AUTH_FAILED
        assert result.http_status == status_code

    @pytest.mark.asyncio
    async def test_fetch_server_error(self, instance: StormglassInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(500, json={"message": "boom"}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_fetch_non_dict_payload(self, instance: StormglassInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=[1, 2, 3]),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.PARSE
        assert result.message == "Unexpected Stormglass payload"

    @pytest.mark.asyncio
    async def test_non_dict_hour_rows_are_skipped(
        self,
        instance: StormglassInstance,
    ) -> None:
        mock_response = {
            "hours": [
                "not-a-row",
                42,
                None,
                {
                    "time": "2024-01-01T00:00:00+00:00",
                    "airTemperature": {"sg": 12.0},
                },
            ],
        }
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=mock_response),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts) == 1
        assert len(result.forecasts[0].hourly) == 1
        assert result.forecasts[0].hourly[0].temperature == 12.0

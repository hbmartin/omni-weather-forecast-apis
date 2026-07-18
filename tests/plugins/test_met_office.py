"""Tests for the Met Office Global Spot plugin using httpx2 mocks."""

from __future__ import annotations

from datetime import date

import httpx2
import pytest
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.met_office import (
    MetOfficeConfig,
    MetOfficeInstance,
    met_office_plugin,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
    ProviderId,
    WeatherCondition,
)

HOURLY_ENTRY = {
    "time": "2026-07-18T12:00Z",
    "screenTemperature": 21.5,
    "feelsLikeTemperature": 20.9,
    "screenDewPointTemperature": 12.3,
    "screenRelativeHumidity": 55.0,
    "windSpeed10m": 4.2,
    "windGustSpeed10m": 7.9,
    "windDirectionFrom10m": 250,
    "visibility": 20000,
    "mslp": 101320,
    "uvIndex": 6,
    "significantWeatherCode": 10,
    "precipitationRate": 0.4,
    "totalPrecipAmount": 1.2,
    "totalSnowAmount": 0.5,
    "probOfPrecipitation": 60,
}

DAILY_ENTRY = {
    "time": "2026-07-18T00:00Z",
    "dayMaxScreenTemperature": 24.0,
    "nightMinScreenTemperature": 11.0,
    "dayMaxFeelsLikeTemp": 23.1,
    "nightMinFeelsLikeTemp": 10.2,
    "midday10MWindSpeed": 3.0,
    "midnight10MWindSpeed": 5.0,
    "midday10MWindGust": 6.0,
    "midnight10MWindGust": 9.0,
    "midday10MWindDirection": 240,
    "middayRelativeHumidity": 48.0,
    "maxUvIndex": 7,
    "daySignificantWeatherCode": 3,
    "nightSignificantWeatherCode": 2,
    "dayProbabilityOfPrecipitation": 20,
    "nightProbabilityOfPrecipitation": 45,
}
PAST_DAILY_ENTRY = {
    **DAILY_ENTRY,
    "time": "2026-07-17T00:00Z",
}


def _geojson(entries: list[object]) -> dict[str, object]:
    return {"features": [{"properties": {"timeSeries": entries}}]}


def _fetch_params(
    granularity: list[Granularity] | None = None,
) -> PluginFetchParams:
    return PluginFetchParams(
        latitude=34.0,
        longitude=-117.0,
        granularity=granularity or [Granularity.HOURLY, Granularity.DAILY],
    )


class TestMetOfficePlugin:
    def test_plugin_id(self) -> None:
        assert met_office_plugin.id == ProviderId.MET_OFFICE

    def test_plugin_name(self) -> None:
        assert met_office_plugin.name == "Met Office"

    def test_validate_config(self) -> None:
        config = met_office_plugin.validate_config({"api_key": "test-key"})
        assert isinstance(config, MetOfficeConfig)
        assert config.api_key == "test-key"

    def test_validate_config_missing_key(self) -> None:
        with pytest.raises(ValidationError):
            met_office_plugin.validate_config({})

    def test_validate_config_empty_key(self) -> None:
        with pytest.raises(ValidationError):
            met_office_plugin.validate_config({"api_key": ""})


class TestMetOfficeInstance:
    @pytest.fixture
    def instance(self) -> MetOfficeInstance:
        return MetOfficeInstance(MetOfficeConfig(api_key="test-key"))

    def test_provider_id(self, instance: MetOfficeInstance) -> None:
        assert instance.provider_id == ProviderId.MET_OFFICE

    def test_capabilities(self, instance: MetOfficeInstance) -> None:
        caps = instance.get_capabilities()
        assert caps.granularity_minutely is False
        assert caps.granularity_hourly is True
        assert caps.granularity_daily is True
        assert caps.max_horizon_hourly_hours == 48
        assert caps.max_horizon_daily_days == 6
        assert caps.requires_api_key is True
        assert caps.alerts is False

    @pytest.mark.asyncio
    async def test_fetch_success(self, instance: MetOfficeInstance) -> None:
        captured_headers: dict[str, str] = {}
        captured_params: dict[str, str] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured_headers.update(dict(request.headers))
            captured_params.update(dict(request.url.params))
            if request.url.path.endswith("/hourly"):
                return httpx2.Response(200, json=_geojson([HOURLY_ENTRY]))
            return httpx2.Response(
                200,
                json=_geojson([PAST_DAILY_ENTRY, DAILY_ENTRY]),
            )

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert captured_headers["apikey"] == "test-key"
        assert captured_params["latitude"] == "34.0"
        assert captured_params["longitude"] == "-117.0"
        assert captured_params["excludeParameterMetadata"] == "true"

        assert isinstance(result, PluginFetchSuccess)
        forecast = result.forecasts[0]
        assert forecast.source.provider == ProviderId.MET_OFFICE

        point = forecast.hourly[0]
        assert point.temperature == 21.5
        assert point.apparent_temperature == 20.9
        assert point.dew_point == 12.3
        assert point.humidity == 55.0
        assert point.wind_speed == 4.2
        assert point.wind_gust == 7.9
        assert point.wind_direction == 250.0
        assert point.visibility == 20.0
        assert point.pressure_sea == 1013.2
        assert point.uv_index == 6.0
        assert point.precipitation == 1.2
        assert point.snow == 0.5
        assert point.precipitation_probability == 0.6
        assert point.condition == WeatherCondition.LIGHT_RAIN
        assert point.condition_code_original == 10
        assert point.is_day is True

        day = forecast.daily[0]
        assert day.date == date(2026, 7, 18)
        assert day.temperature_max == 24.0
        assert day.temperature_min == 11.0
        assert day.apparent_temperature_max == 23.1
        assert day.apparent_temperature_min == 10.2
        assert day.wind_speed_max == 5.0
        assert day.wind_gust_max == 9.0
        assert day.wind_direction_dominant == 240.0
        assert day.uv_index_max == 7.0
        assert day.precipitation_probability_max == 0.45
        assert day.condition == WeatherCondition.PARTLY_CLOUDY
        assert day.humidity_mean is None

    @pytest.mark.asyncio
    async def test_daily_drops_historical_row_and_returns_six_future_days(
        self,
        instance: MetOfficeInstance,
    ) -> None:
        entries = [
            {
                **DAILY_ENTRY,
                "time": f"2026-07-{day:02d}T00:00Z",
            }
            for day in range(17, 24)
        ]
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=_geojson(entries)),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.DAILY]),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert [point.date for point in result.forecasts[0].daily] == [
            date(2026, 7, day) for day in range(18, 24)
        ]

    @pytest.mark.asyncio
    async def test_hourly_only_skips_daily_endpoint(
        self,
        instance: MetOfficeInstance,
    ) -> None:
        requested_paths: list[str] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            requested_paths.append(request.url.path)
            return httpx2.Response(200, json=_geojson([HOURLY_ENTRY]))

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.HOURLY]),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert requested_paths == ["/sitespecific/v0/point/hourly"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [401, 403])
    async def test_fetch_auth_error(
        self,
        instance: MetOfficeInstance,
        status_code: int,
    ) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(status_code, json={"message": "denied"}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.AUTH_FAILED
        assert result.http_status == status_code

    @pytest.mark.asyncio
    async def test_fetch_server_error(self, instance: MetOfficeInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(500, json={"message": "boom"}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_fetch_non_dict_payload(self, instance: MetOfficeInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=[1, 2, 3]),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.HOURLY]),
                client,
            )

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.PARSE
        assert result.message == "Unexpected Met Office hourly payload"

    @pytest.mark.asyncio
    async def test_missing_features_yields_no_data(
        self,
        instance: MetOfficeInstance,
    ) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json={"type": "FeatureCollection"}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NO_DATA

    @pytest.mark.asyncio
    async def test_non_dict_rows_are_skipped(
        self,
        instance: MetOfficeInstance,
    ) -> None:
        payload = _geojson(["not-a-row", 42, None, HOURLY_ENTRY])
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=payload),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.HOURLY]),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts[0].hourly) == 1

    @pytest.mark.asyncio
    async def test_include_raw_captures_payloads(
        self,
        instance: MetOfficeInstance,
    ) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            if request.url.path.endswith("/hourly"):
                return httpx2.Response(200, json=_geojson([HOURLY_ENTRY]))
            return httpx2.Response(
                200,
                json=_geojson([PAST_DAILY_ENTRY, DAILY_ENTRY]),
            )

        transport = httpx2.MockTransport(handler)
        params = PluginFetchParams(
            latitude=34.0,
            longitude=-117.0,
            granularity=[Granularity.HOURLY, Granularity.DAILY],
            include_raw=True,
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        assert isinstance(result.raw, dict)
        assert set(result.raw) == {"hourly", "daily"}

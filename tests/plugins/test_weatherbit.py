"""Tests for Weatherbit condition mapping and plugin behavior."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime

import httpx2
import pytest
import pytest_asyncio
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.weatherbit import (
    WeatherbitConfig,
    _map_condition,
    weatherbit_plugin,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
    PluginInstance,
    ProviderId,
    WeatherCondition,
)

_HOURLY_PATH = "/v2.0/forecast/hourly"
_DAILY_PATH = "/v2.0/forecast/daily"


def test_code_233_maps_to_hail() -> None:
    assert _map_condition("Thunderstorm with hail", 233) == WeatherCondition.HAIL


def test_code_none_falls_back_to_text() -> None:
    assert _map_condition("light rain", None) == WeatherCondition.LIGHT_RAIN


def test_code_none_without_text_is_none() -> None:
    assert _map_condition(None, None) is None


def test_unmapped_code_falls_back_to_text() -> None:
    assert _map_condition("heavy snow", 999) == WeatherCondition.HEAVY_SNOW


def test_unmapped_code_without_text_is_none() -> None:
    assert _map_condition(None, 999) is None


def test_mapped_code_wins_over_text() -> None:
    assert _map_condition("clear sky", 502) == WeatherCondition.HEAVY_RAIN


def _fetch_params(granularity: list[Granularity]) -> PluginFetchParams:
    return PluginFetchParams(
        latitude=34.0,
        longitude=-117.0,
        granularity=granularity,
    )


class TestWeatherbitPlugin:
    def test_plugin_id(self) -> None:
        assert weatherbit_plugin.id == ProviderId.WEATHERBIT

    def test_validate_config_defaults(self) -> None:
        config = weatherbit_plugin.validate_config({"api_key": "test-key"})
        assert isinstance(config, WeatherbitConfig)
        assert config.api_key == "test-key"
        assert config.hours == 48
        assert config.units == "M"

    def test_validate_config_missing_key(self) -> None:
        with pytest.raises(ValidationError):
            weatherbit_plugin.validate_config({})

    @pytest.mark.parametrize("hours", [1, 240])
    def test_hours_bounds_accepted(self, hours: int) -> None:
        config = weatherbit_plugin.validate_config(
            {"api_key": "test-key", "hours": hours},
        )
        assert config.hours == hours

    @pytest.mark.parametrize("hours", [0, 241, -5])
    def test_hours_out_of_bounds_rejected(self, hours: int) -> None:
        with pytest.raises(ValidationError):
            weatherbit_plugin.validate_config({"api_key": "test-key", "hours": hours})

    @pytest.mark.parametrize("units", ["M", "S", "I"])
    def test_units_literals_accepted(self, units: str) -> None:
        config = weatherbit_plugin.validate_config(
            {"api_key": "test-key", "units": units},
        )
        assert config.units == units

    def test_invalid_units_rejected(self) -> None:
        with pytest.raises(ValidationError):
            weatherbit_plugin.validate_config({"api_key": "test-key", "units": "X"})


class TestWeatherbitInstance:
    @pytest_asyncio.fixture
    async def instance(self) -> PluginInstance:
        config = weatherbit_plugin.validate_config({"api_key": "test-key"})
        return await weatherbit_plugin.initialize(config)

    def test_provider_id(self, instance: PluginInstance) -> None:
        assert instance.provider_id == ProviderId.WEATHERBIT

    def test_capabilities(self, instance: PluginInstance) -> None:
        caps = instance.get_capabilities()
        assert caps.granularity_hourly is True
        assert caps.granularity_daily is True
        assert caps.max_horizon_hourly_hours == 240
        assert caps.max_horizon_daily_days == 16

    @pytest.mark.asyncio
    async def test_fetch_success_hourly_and_daily(
        self,
        instance: PluginInstance,
    ) -> None:
        hourly_payload = {
            "data": [
                {
                    "timestamp_utc": "2024-01-01T00:00:00",
                    "temp": 12.5,
                    "app_temp": 11.0,
                    "dewpt": 8.7,
                    "rh": 78,
                    "wind_spd": 4.2,
                    "wind_gust_spd": 7.9,
                    "wind_dir": 210,
                    "slp": 1015.2,
                    "pres": 1002.1,
                    "precip": 0.4,
                    "snow": 0,
                    "pop": 40,
                    "clouds": 65,
                    "vis": 16.0,
                    "uv": 2.3,
                    "weather": {"code": 501, "description": "Moderate rain"},
                },
                "not-a-mapping",
            ],
            "city_name": "Testville",
        }
        daily_payload = {
            "data": [
                {
                    "valid_date": "2024-01-01",
                    "max_temp": 14.0,
                    "min_temp": 4.5,
                    "app_max_temp": 13.0,
                    "app_min_temp": 3.0,
                    "max_wind_spd": 9.5,
                    "max_wind_gust_spd": 15.0,
                    "wind_dir": 200,
                    "precip": 1.2,
                    "snow": 0,
                    "pop": 55,
                    "clouds": 40,
                    "rh": 70,
                    "slp": 1014.0,
                    "uv": 3.4,
                    "vis": 20.0,
                    "sunrise_ts": 1704096000,
                    "sunset_ts": 1704128400,
                    "moonrise_ts": 1704110000,
                    "moonset_ts": 1704150000,
                    "moon_phase": 0.62,
                    "weather": {"code": 802, "description": "Scattered clouds"},
                },
            ],
        }

        captured: dict[str, dict[str, str]] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured[request.url.path] = dict(request.url.params)
            if request.url.path == _HOURLY_PATH:
                return httpx2.Response(200, json=hourly_payload)
            if request.url.path == _DAILY_PATH:
                return httpx2.Response(200, json=daily_payload)
            return httpx2.Response(404)

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.HOURLY, Granularity.DAILY]),
                client,
            )

        assert captured[_HOURLY_PATH] == {
            "lat": "34.0",
            "lon": "-117.0",
            "hours": "48",
            "units": "M",
            "key": "test-key",
        }
        assert captured[_DAILY_PATH] == {
            "lat": "34.0",
            "lon": "-117.0",
            "units": "M",
            "key": "test-key",
        }

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts) == 1
        forecast = result.forecasts[0]
        assert forecast.source.provider == ProviderId.WEATHERBIT

        assert len(forecast.hourly) == 1
        hour = forecast.hourly[0]
        assert hour.timestamp == datetime(2024, 1, 1, tzinfo=UTC)
        assert hour.temperature == 12.5
        assert hour.apparent_temperature == 11.0
        assert hour.dew_point == 8.7
        assert hour.humidity == 78.0
        assert hour.wind_speed == 4.2
        assert hour.wind_gust == 7.9
        assert hour.wind_direction == 210.0
        assert hour.pressure_sea == 1015.2
        assert hour.pressure_surface == 1002.1
        assert hour.precipitation == 0.4
        assert hour.precipitation_probability == pytest.approx(0.4)
        assert hour.cloud_cover == 65.0
        assert hour.visibility == 16.0
        assert hour.uv_index == 2.3
        assert hour.condition == WeatherCondition.RAIN
        assert hour.condition_original == "Moderate rain"
        assert hour.condition_code_original == 501

        assert len(forecast.daily) == 1
        day = forecast.daily[0]
        assert day.date == date(2024, 1, 1)
        assert day.temperature_max == 14.0
        assert day.temperature_min == 4.5
        assert day.apparent_temperature_max == 13.0
        assert day.apparent_temperature_min == 3.0
        assert day.wind_speed_max == 9.5
        assert day.wind_gust_max == 15.0
        assert day.wind_direction_dominant == 200.0
        assert day.precipitation_sum == 1.2
        assert day.precipitation_probability_max == pytest.approx(0.55)
        assert day.cloud_cover_mean == 40.0
        assert day.humidity_mean == 70.0
        assert day.pressure_sea_mean == 1014.0
        assert day.uv_index_max == 3.4
        assert day.visibility_min == 20.0
        assert day.sunrise == datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
        assert day.sunset == datetime(2024, 1, 1, 17, 0, tzinfo=UTC)
        assert day.moon_phase == 0.62
        assert day.condition == WeatherCondition.PARTLY_CLOUDY
        assert day.summary == "Scattered clouds"

    @pytest.mark.asyncio
    async def test_fetch_imperial_units_converted(self) -> None:
        config = weatherbit_plugin.validate_config(
            {"api_key": "test-key", "units": "I"},
        )
        instance = await weatherbit_plugin.initialize(config)

        hourly_payload = {
            "data": [
                {
                    "timestamp_utc": "2024-01-01T00:00:00",
                    "temp": 68.0,
                    "app_temp": 59.0,
                    "dewpt": 41.0,
                    "rh": 50,
                    "wind_spd": 10.0,
                    "wind_gust_spd": 20.0,
                    "precip": 0.5,
                    "snow": 0.2,
                    "snow_depth": 4.0,
                    "vis": 10.0,
                },
            ],
        }

        captured_params: dict[str, str] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured_params.update(dict(request.url.params))
            return httpx2.Response(200, json=hourly_payload)

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.HOURLY]),
                client,
            )

        assert captured_params["units"] == "I"
        assert isinstance(result, PluginFetchSuccess)
        hour = result.forecasts[0].hourly[0]
        # Fahrenheit converted to Celsius via celsius_from_fahrenheit
        assert hour.temperature == pytest.approx(20.0)
        assert hour.apparent_temperature == pytest.approx(15.0)
        assert hour.dew_point == pytest.approx(5.0)
        # mph converted to m/s via ms_from_mph
        assert hour.wind_speed == pytest.approx(4.4704)
        assert hour.wind_gust == pytest.approx(8.9408)
        # inches converted to mm via mm_from_inches
        assert hour.precipitation == pytest.approx(12.7)
        assert hour.snow == pytest.approx(5.08)
        # Regression: imperial snow depth (inches) and visibility (miles)
        # used to pass through unconverted.
        assert hour.snow_depth == pytest.approx(101.6)
        assert hour.visibility == pytest.approx(16.0934)
        # humidity is unit-independent
        assert hour.humidity == 50.0

    @pytest.mark.asyncio
    async def test_fetch_scientific_units_converts_kelvin(self) -> None:
        config = weatherbit_plugin.validate_config(
            {"api_key": "test-key", "units": "S"},
        )
        instance = await weatherbit_plugin.initialize(config)

        hourly_payload = {
            "data": [
                {
                    "timestamp_utc": "2024-01-01T00:00:00",
                    "temp": 293.15,
                    "app_temp": 288.15,
                    "dewpt": 278.15,
                    "wind_spd": 4.0,
                    "vis": 16.0,
                },
            ],
        }

        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=hourly_payload)
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.HOURLY]),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        hour = result.forecasts[0].hourly[0]
        # Regression: Kelvin used to pass through into the Celsius fields.
        assert hour.temperature == pytest.approx(20.0)
        assert hour.apparent_temperature == pytest.approx(15.0)
        assert hour.dew_point == pytest.approx(5.0)
        # Scientific wind (m/s) and visibility (km) pass through unchanged.
        assert hour.wind_speed == 4.0
        assert hour.visibility == 16.0

    @pytest.mark.asyncio
    async def test_daily_only_skips_hourly_endpoint(
        self,
        instance: PluginInstance,
    ) -> None:
        calls: Counter[str] = Counter()

        def handler(request: httpx2.Request) -> httpx2.Response:
            calls[request.url.path] += 1
            return httpx2.Response(200, json={"data": []})

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.DAILY]),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert calls[_HOURLY_PATH] == 0
        assert calls[_DAILY_PATH] == 1

    @pytest.mark.asyncio
    async def test_hourly_only_skips_daily_endpoint(
        self,
        instance: PluginInstance,
    ) -> None:
        calls: Counter[str] = Counter()

        def handler(request: httpx2.Request) -> httpx2.Response:
            calls[request.url.path] += 1
            return httpx2.Response(200, json={"data": []})

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.HOURLY]),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert calls[_HOURLY_PATH] == 1
        assert calls[_DAILY_PATH] == 0

    @pytest.mark.asyncio
    async def test_fetch_hourly_auth_error(self, instance: PluginInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(401, json={"error": "Invalid API key"}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.HOURLY]),
                client,
            )

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.AUTH_FAILED
        assert result.http_status == 401

    @pytest.mark.asyncio
    async def test_fetch_hourly_list_payload(self, instance: PluginInstance) -> None:
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
        assert result.message == "Unexpected Weatherbit hourly payload"

    @pytest.mark.asyncio
    async def test_fetch_daily_list_payload(self, instance: PluginInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=[1, 2, 3]),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.DAILY]),
                client,
            )

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.PARSE
        assert result.message == "Unexpected Weatherbit daily payload"

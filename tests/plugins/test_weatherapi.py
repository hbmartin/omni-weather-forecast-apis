"""Tests for WeatherAPI.com plugin using httpx2 mocks."""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx2
import pytest
import pytest_asyncio
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.weatherapi import (
    WeatherAPIConfig,
    weatherapi_plugin,
)
from omni_weather_forecast_apis.types import (
    AlertSeverity,
    ErrorCode,
    Granularity,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
    ProviderId,
    WeatherCondition,
)


class TestWeatherAPIPlugin:
    def test_plugin_id(self):
        assert weatherapi_plugin._id == ProviderId.WEATHERAPI
        assert weatherapi_plugin.id == ProviderId.WEATHERAPI

    def test_plugin_name(self):
        assert weatherapi_plugin.name == "WeatherAPI.com"

    def test_validate_config_defaults(self):
        config = weatherapi_plugin.validate_config({"api_key": "test-key"})
        assert isinstance(config, WeatherAPIConfig)
        assert config.api_key == "test-key"
        assert config.days == 7
        assert config.aqi is False
        assert config.alerts is True

    def test_validate_config_missing_api_key(self):
        with pytest.raises(ValidationError):
            weatherapi_plugin.validate_config({})

    def test_validate_config_empty_api_key(self):
        with pytest.raises(ValidationError):
            weatherapi_plugin.validate_config({"api_key": ""})

    @pytest.mark.parametrize("days", [0, -1, 15])
    def test_validate_config_days_out_of_range(self, days):
        with pytest.raises(ValidationError):
            weatherapi_plugin.validate_config({"api_key": "test-key", "days": days})

    @pytest.mark.parametrize("days", [1, 14])
    def test_validate_config_days_bounds_accepted(self, days):
        config = weatherapi_plugin.validate_config(
            {"api_key": "test-key", "days": days},
        )
        assert config.days == days


class TestWeatherAPIInstance:
    @pytest_asyncio.fixture
    async def instance(self):
        config = weatherapi_plugin.validate_config({"api_key": "test-key"})
        return await weatherapi_plugin.initialize(config)

    def test_provider_id(self, instance):
        assert instance.provider_id == ProviderId.WEATHERAPI

    def test_capabilities(self, instance):
        caps = instance.get_capabilities()
        assert caps.granularity_minutely is False
        assert caps.granularity_hourly is True
        assert caps.granularity_daily is True
        assert caps.max_horizon_hourly_hours == 336
        assert caps.max_horizon_daily_days == 14
        assert caps.alerts is True
        assert caps.requires_api_key is True

    @pytest.mark.asyncio
    async def test_fetch_success(self, instance):
        mock_response = {
            "location": {
                "name": "Rancho Cucamonga",
                "region": "California",
                "country": "USA",
                "lat": 34.0,
                "lon": -117.0,
                "tz_id": "America/Los_Angeles",
                "localtime_epoch": 1704067200,
                "localtime": "2023-12-31 16:00",
            },
            "forecast": {
                "forecastday": [
                    {
                        "date": "2024-01-01",
                        "date_epoch": 1704067200,
                        "day": {
                            "maxtemp_c": 25.5,
                            "mintemp_c": 10.2,
                            "avgtemp_c": 17.8,
                            "maxwind_kph": 28.8,
                            "totalprecip_mm": 4.2,
                            "avgvis_km": 9.5,
                            "avghumidity": 60,
                            "daily_will_it_rain": 1,
                            "daily_chance_of_rain": 80,
                            "daily_will_it_snow": 0,
                            "daily_chance_of_snow": 0,
                            "condition": {"text": "Light rain", "code": 1183},
                            "uv": 6.0,
                        },
                        "astro": {
                            "sunrise": "06:58 AM",
                            "sunset": "04:49 PM",
                            "moonrise": "09:22 PM",
                            "moonset": "10:47 AM",
                            "moon_phase": "Waning Gibbous",
                        },
                        "hour": [
                            {
                                "time_epoch": 1704067200,
                                "time": "2024-01-01 00:00",
                                "temp_c": 20.5,
                                "is_day": 1,
                                "condition": {"text": "Partly cloudy", "code": 1003},
                                "wind_kph": 18.0,
                                "wind_degree": 180,
                                "wind_dir": "S",
                                "pressure_mb": 1013.0,
                                "precip_mm": 0.4,
                                "humidity": 65,
                                "cloud": 50,
                                "feelslike_c": 19.0,
                                "dewpoint_c": 12.5,
                                "vis_km": 10.0,
                                "gust_kph": 36.0,
                                "uv": 5.0,
                                "chance_of_rain": 75,
                                "chance_of_snow": 0,
                            },
                            {
                                "time_epoch": 1704070800,
                                "time": "2024-01-01 01:00",
                                "temp_c": 19.0,
                                "is_day": 0,
                                "condition": {"text": "Clear", "code": 1000},
                                "wind_kph": 7.2,
                            },
                        ],
                    },
                    {
                        "date": "2024-01-02",
                        "date_epoch": 1704153600,
                        "day": {
                            "maxtemp_c": 18.0,
                            "mintemp_c": 9.0,
                            "condition": {"text": "Overcast", "code": 1009},
                        },
                        "hour": [
                            {
                                "time_epoch": 1704153600,
                                "temp_c": 15.0,
                                "is_day": 1,
                                "condition": {"text": "Overcast", "code": 1009},
                            },
                        ],
                    },
                ],
            },
            "alerts": {
                "alert": [
                    {
                        "headline": "Flood Warning issued January 1",
                        "msgtype": "Alert",
                        "severity": "Moderate",
                        "urgency": "Expected",
                        "areas": "San Bernardino County",
                        "category": "Met",
                        "event": "Flood Warning",
                        "effective": "2024-01-01T06:00:00-08:00",
                        "expires": "2024-01-02T12:00:00-08:00",
                        "desc": "Heavy rain may cause flooding.",
                        "instruction": "Move to higher ground.",
                    },
                ],
            },
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
        forecast = result.forecasts[0]
        assert forecast.source.provider == ProviderId.WEATHERAPI

        assert len(forecast.hourly) == 3
        hour = forecast.hourly[0]
        assert hour.timestamp == datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        assert hour.timestamp_unix == 1704067200
        assert hour.temperature == 20.5
        assert hour.apparent_temperature == 19.0
        assert hour.dew_point == 12.5
        assert hour.humidity == 65.0
        assert hour.wind_speed == pytest.approx(5.0)  # 18 km/h -> m/s
        assert hour.wind_gust == pytest.approx(10.0)  # 36 km/h -> m/s
        assert hour.wind_direction == 180.0
        assert hour.pressure_sea == 1013.0
        assert hour.precipitation == 0.4
        assert hour.rain == 0.4
        assert hour.precipitation_probability == 0.75
        assert hour.cloud_cover == 50.0
        assert hour.visibility == 10.0
        assert hour.uv_index == 5.0
        assert hour.condition == WeatherCondition.PARTLY_CLOUDY
        assert hour.condition_original == "Partly cloudy"
        assert hour.condition_code_original == 1003
        assert hour.is_day is True

        night = forecast.hourly[1]
        assert night.is_day is False
        assert night.wind_speed == pytest.approx(2.0)  # 7.2 km/h -> m/s
        assert night.condition == WeatherCondition.CLEAR
        assert night.precipitation is None

        assert len(forecast.daily) == 2
        day = forecast.daily[0]
        assert day.date == date(2024, 1, 1)
        assert day.temperature_max == 25.5
        assert day.temperature_min == 10.2
        assert day.apparent_temperature_max == 25.5
        assert day.apparent_temperature_min == 10.2
        assert day.wind_speed_max == pytest.approx(8.0)  # 28.8 km/h -> m/s
        assert day.precipitation_sum == 4.2
        assert day.rain_sum == 4.2
        assert day.precipitation_probability_max == 0.8
        assert day.uv_index_max == 6.0
        assert day.visibility_min == 9.5
        assert day.humidity_mean == 60.0
        assert day.condition == WeatherCondition.LIGHT_RAIN
        assert day.summary == "Light rain"
        # The astro block (12-hour clock strings) is not parsed.
        assert day.sunrise is None
        assert day.sunset is None
        assert forecast.daily[1].date == date(2024, 1, 2)
        assert forecast.daily[1].temperature_max == 18.0

        assert len(forecast.alerts) == 1
        alert = forecast.alerts[0]
        assert alert.sender_name == "WeatherAPI.com"
        assert alert.event == "Flood Warning"
        assert alert.start == datetime(2024, 1, 1, 14, 0, tzinfo=UTC)
        assert alert.end == datetime(2024, 1, 2, 20, 0, tzinfo=UTC)
        assert alert.description == "Heavy rain may cause flooding."
        assert alert.severity == AlertSeverity.MODERATE

    @pytest.mark.asyncio
    async def test_fetch_request_params(self):
        config = weatherapi_plugin.validate_config(
            {"api_key": "secret-key", "days": 3},
        )
        instance = await weatherapi_plugin.initialize(config)
        captured = {}

        def handler(request):
            captured["url"] = request.url
            captured["params"] = dict(request.url.params)
            return httpx2.Response(200, json={})

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY, Granularity.DAILY],
                language="es",
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        assert captured["url"].host == "api.weatherapi.com"
        assert captured["url"].path == "/v1/forecast.json"
        assert captured["params"]["key"] == "secret-key"
        assert captured["params"]["q"] == "34.0,-117.0"
        assert captured["params"]["days"] == "3"
        assert captured["params"]["aqi"] == "no"
        assert captured["params"]["alerts"] == "yes"
        assert captured["params"]["lang"] == "es"

    @pytest.mark.asyncio
    async def test_fetch_empty_payload(self, instance):
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json={}),
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
        assert result.forecasts[0].hourly == []
        assert result.forecasts[0].daily == []
        assert result.forecasts[0].alerts == []

    @pytest.mark.asyncio
    async def test_fetch_auth_error(self, instance):
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(
                401,
                json={"error": {"code": 2006, "message": "API key is invalid."}},
            ),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchError)
        assert result.status == "error"
        assert result.code == ErrorCode.AUTH_FAILED
        assert result.http_status == 401

    @pytest.mark.asyncio
    async def test_fetch_server_error(self, instance):
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(500, json={"error": "internal"}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NETWORK
        assert result.http_status == 500

    @pytest.mark.asyncio
    async def test_fetch_non_dict_payload(self, instance):
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=[1, 2]),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.PARSE
        assert result.message == "Unexpected WeatherAPI payload"
        assert result.raw == [1, 2]

    @pytest.mark.asyncio
    async def test_fetch_undecodable_body(self, instance):
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, content=b"not json"),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.PARSE
        assert result.message.startswith("Could not decode JSON")

    @pytest.mark.asyncio
    async def test_fetch_skips_malformed_rows(self, instance):
        mock_response = {
            "forecast": {
                "forecastday": [
                    {
                        "date": "2024-01-01",
                        "day": {"maxtemp_c": 21.0, "mintemp_c": 8.0},
                        "hour": [
                            {"temp_c": 11.0},  # missing time_epoch -> skipped
                            "not-a-mapping",  # skipped
                            {"time_epoch": 1704067200, "temp_c": 12.0},
                        ],
                    },
                    {"day": {"maxtemp_c": 20.0}},  # missing date -> skipped
                    "bogus",  # non-mapping day -> skipped
                ],
            },
            "alerts": {
                "alert": [
                    {"event": "No effective time"},  # missing effective -> skipped
                    "junk",  # non-mapping alert -> skipped
                ],
            },
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
        forecast = result.forecasts[0]
        assert len(forecast.hourly) == 1
        assert forecast.hourly[0].temperature == 12.0
        assert len(forecast.daily) == 1
        assert forecast.daily[0].date == date(2024, 1, 1)
        assert forecast.alerts == []

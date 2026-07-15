"""Tests for Visual Crossing plugin using httpx2 mocks."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx2
import pytest
import pytest_asyncio
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.visual_crossing import (
    VisualCrossingConfig,
    visual_crossing_plugin,
)
from omni_weather_forecast_apis.types import (
    AlertSeverity,
    ErrorCode,
    Granularity,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
    PluginInstance,
    ProviderId,
    WeatherCondition,
)

_JAN_1_MIDNIGHT = 1704067200  # 2024-01-01T00:00:00Z
_JAN_1_4AM = 1704081600  # 2024-01-01T04:00:00Z (before sunrise)
_JAN_1_SUNRISE = 1704092400  # 2024-01-01T07:00:00Z
_JAN_1_NOON = 1704110400  # 2024-01-01T12:00:00Z (daylight)
_JAN_1_SUNSET = 1704128400  # 2024-01-01T17:00:00Z
_JAN_2_MIDNIGHT = 1704153600  # 2024-01-02T00:00:00Z


def _forecast_params(**overrides: Any) -> PluginFetchParams:
    base: dict[str, Any] = {
        "latitude": 34.0,
        "longitude": -117.0,
        "granularity": [Granularity.HOURLY, Granularity.DAILY],
    }
    return PluginFetchParams(**{**base, **overrides})


async def _fetch(
    instance: PluginInstance,
    transport: httpx2.MockTransport,
    params: PluginFetchParams | None = None,
) -> PluginFetchResult:
    async with httpx2.AsyncClient(transport=transport) as client:
        return await instance.fetch_forecast(params or _forecast_params(), client)


def _timeline_payload() -> dict[str, Any]:
    """Realistic Visual Crossing timeline response (metric unit group)."""

    return {
        "queryCost": 1,
        "latitude": 34.0,
        "longitude": -117.0,
        "resolvedAddress": "34.0,-117.0",
        "address": "34.0,-117.0",
        "timezone": "America/Los_Angeles",
        "tzoffset": -8.0,
        "days": [
            {
                "datetime": "2024-01-01",
                "datetimeEpoch": _JAN_1_MIDNIGHT,
                "tempmax": 25.5,
                "tempmin": 10.25,
                "feelslikemax": 24.0,
                "feelslikemin": 8.5,
                "humidity": 55.0,
                "precip": 4.2,
                "precipprob": 75.0,
                "windgust": 36.0,
                "windspeed": 18.0,
                "winddir": 225.0,
                "pressure": 1016.2,
                "cloudcover": 40.0,
                "visibility": 24.1,
                "uvindex": 6.0,
                "solarenergy": 12.3,
                "moonphase": 0.5,
                "sunrise": "07:00:00",
                "sunriseEpoch": _JAN_1_SUNRISE,
                "sunset": "17:00:00",
                "sunsetEpoch": _JAN_1_SUNSET,
                "conditions": "Rain, Partially cloudy",
                "icon": "rain",
                "hours": [
                    {
                        "datetime": "04:00:00",
                        "datetimeEpoch": _JAN_1_4AM,
                        "temp": 12.5,
                        "feelslike": 11.0,
                        "dew": 8.0,
                        "humidity": 82.0,
                        "precip": 0.0,
                        "precipprob": 5.0,
                        "windgust": 54.0,
                        "windspeed": 36.0,
                        "winddir": 190.0,
                        "pressure": 1015.0,
                        "cloudcover": 25.0,
                        "visibility": 16.0,
                        "uvindex": 0.0,
                        "solarradiation": 0.0,
                        "conditions": "Clear",
                        "icon": "clear-night",
                    },
                    {
                        "datetime": "12:00:00",
                        "datetimeEpoch": _JAN_1_NOON,
                        "temp": 20.0,
                        "feelslike": 19.5,
                        "humidity": 60.0,
                        "precip": 1.4,
                        "precipprob": 80.0,
                        "winddir": 200.0,
                        "pressure": 1013.5,
                        "cloudcover": 90.0,
                        "visibility": 9.9,
                        "uvindex": 4.0,
                        "solarradiation": 350.0,
                        "conditions": "Rain",
                        "icon": "rain",
                    },
                ],
            },
            {
                "datetime": "2024-01-02",
                "datetimeEpoch": _JAN_2_MIDNIGHT,
                "tempmax": 18.0,
                "tempmin": 7.0,
                "windspeed": 27.0,
                "precip": 0.0,
                "precipprob": 10.0,
                "sunriseEpoch": _JAN_2_MIDNIGHT + 7 * 3600,
                "sunsetEpoch": _JAN_2_MIDNIGHT + 17 * 3600,
                "conditions": "Clear",
                "icon": "clear-day",
            },
        ],
        "alerts": [
            {
                "event": "Flood Watch",
                "headline": "Flood Watch until further notice",
                "description": "Heavy rain may cause flooding.",
                "severity": "Severe",
                "onsetEpoch": _JAN_1_MIDNIGHT,
                "endsEpoch": _JAN_2_MIDNIGHT,
                "link": "https://alerts.example/flood-watch",
                "source": "NWS",
            },
            {
                "onset": "2024-01-01T06:00:00Z",
            },
        ],
    }


class TestVisualCrossingPlugin:
    def test_plugin_id(self) -> None:
        assert visual_crossing_plugin.id == ProviderId.VISUAL_CROSSING

    def test_plugin_name(self) -> None:
        assert visual_crossing_plugin.name == "Visual Crossing"

    def test_validate_config(self) -> None:
        config = visual_crossing_plugin.validate_config({"api_key": "test-key"})
        assert isinstance(config, VisualCrossingConfig)
        assert config.api_key == "test-key"
        assert config.include == "hours,days,alerts"

    def test_validate_config_custom_include(self) -> None:
        config = visual_crossing_plugin.validate_config(
            {"api_key": "test-key", "include": "days"},
        )
        assert config.include == "days"

    def test_validate_config_missing_key(self) -> None:
        with pytest.raises(ValidationError):
            visual_crossing_plugin.validate_config({})

    def test_validate_config_empty_key(self) -> None:
        with pytest.raises(ValidationError):
            visual_crossing_plugin.validate_config({"api_key": ""})


class TestVisualCrossingInstance:
    @pytest_asyncio.fixture
    async def instance(self) -> PluginInstance:
        config = visual_crossing_plugin.validate_config({"api_key": "test-key"})
        return await visual_crossing_plugin.initialize(config)

    def test_provider_id(self, instance: PluginInstance) -> None:
        assert instance.provider_id == ProviderId.VISUAL_CROSSING

    def test_capabilities(self, instance: PluginInstance) -> None:
        caps = instance.get_capabilities()
        assert caps.granularity_minutely is False
        assert caps.granularity_hourly is True
        assert caps.granularity_daily is True
        assert caps.max_horizon_hourly_hours == 360
        assert caps.max_horizon_daily_days == 15
        assert caps.alerts is True
        assert caps.requires_api_key is True

    @pytest.mark.asyncio
    async def test_fetch_success_hourly(self, instance: PluginInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=_timeline_payload()),
        )
        result = await _fetch(instance, transport)

        assert isinstance(result, PluginFetchSuccess)
        assert result.raw is None
        assert len(result.forecasts) == 1
        forecast = result.forecasts[0]
        assert forecast.source.provider == ProviderId.VISUAL_CROSSING
        assert forecast.timezone == "America/Los_Angeles"

        assert len(forecast.hourly) == 2
        night = forecast.hourly[0]
        assert night.timestamp == datetime(2024, 1, 1, 4, 0, tzinfo=UTC)
        assert night.timestamp_unix == _JAN_1_4AM
        assert night.temperature == 12.5
        assert night.apparent_temperature == 11.0
        assert night.dew_point == 8.0
        assert night.humidity == 82.0
        assert night.wind_speed == pytest.approx(10.0)  # 36 km/h -> m/s
        assert night.wind_gust == pytest.approx(15.0)  # 54 km/h -> m/s
        assert night.wind_direction == 190.0
        assert night.pressure_sea == 1015.0
        assert night.precipitation == 0.0
        assert night.precipitation_probability == pytest.approx(0.05)
        assert night.cloud_cover == 25.0
        assert night.visibility == 16.0
        assert night.uv_index == 0.0
        assert night.solar_radiation_ghi == 0.0
        assert night.condition == WeatherCondition.CLEAR
        assert night.condition_original == "Clear"
        assert night.condition_code_original == "clear-night"
        assert night.is_day is False  # 04:00 is before sunriseEpoch

        noon = forecast.hourly[1]
        assert noon.timestamp == datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        assert noon.temperature == 20.0
        assert noon.wind_speed is None  # windspeed absent -> not coerced to 0
        assert noon.wind_gust is None
        assert noon.precipitation == 1.4
        assert noon.precipitation_probability == pytest.approx(0.8)
        assert noon.solar_radiation_ghi == 350.0
        assert noon.condition == WeatherCondition.RAIN
        assert noon.is_day is True  # between sunriseEpoch and sunsetEpoch

    @pytest.mark.asyncio
    async def test_fetch_success_daily(self, instance: PluginInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=_timeline_payload()),
        )
        result = await _fetch(instance, transport)

        assert isinstance(result, PluginFetchSuccess)
        forecast = result.forecasts[0]
        assert len(forecast.daily) == 2

        day = forecast.daily[0]
        assert day.date == date(2024, 1, 1)
        assert day.temperature_max == 25.5
        assert day.temperature_min == 10.25
        assert day.apparent_temperature_max == 24.0
        assert day.apparent_temperature_min == 8.5
        assert day.wind_speed_max == pytest.approx(5.0)  # 18 km/h -> m/s
        assert day.wind_gust_max == pytest.approx(10.0)  # 36 km/h -> m/s
        assert day.wind_direction_dominant == 225.0
        assert day.precipitation_sum == 4.2
        assert day.precipitation_probability_max == pytest.approx(0.75)
        assert day.cloud_cover_mean == 40.0
        assert day.uv_index_max == 6.0
        assert day.visibility_min == 24.1
        assert day.humidity_mean == 55.0
        assert day.pressure_sea_mean == 1016.2
        assert day.condition == WeatherCondition.RAIN
        assert day.summary == "Rain, Partially cloudy"
        assert day.sunrise == datetime(2024, 1, 1, 7, 0, tzinfo=UTC)
        assert day.sunset == datetime(2024, 1, 1, 17, 0, tzinfo=UTC)
        assert day.moon_phase == 0.5
        assert day.solar_radiation_sum == 12.3

        second = forecast.daily[1]
        assert second.date == date(2024, 1, 2)
        assert second.wind_speed_max == pytest.approx(7.5)  # 27 km/h -> m/s
        assert second.precipitation_probability_max == pytest.approx(0.1)
        assert second.condition == WeatherCondition.CLEAR

    @pytest.mark.asyncio
    async def test_fetch_success_alerts(self, instance: PluginInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=_timeline_payload()),
        )
        result = await _fetch(instance, transport)

        assert isinstance(result, PluginFetchSuccess)
        alerts = result.forecasts[0].alerts
        assert len(alerts) == 2

        flood = alerts[0]
        assert flood.sender_name == "NWS"
        assert flood.event == "Flood Watch"
        assert flood.start == datetime(2024, 1, 1, tzinfo=UTC)
        assert flood.end == datetime(2024, 1, 2, tzinfo=UTC)
        assert flood.description == "Heavy rain may cause flooding."
        assert flood.severity == AlertSeverity.SEVERE
        assert flood.url == "https://alerts.example/flood-watch"

        minimal = alerts[1]
        assert minimal.sender_name == "Visual Crossing"
        assert minimal.event == "Alert"
        assert minimal.start == datetime(2024, 1, 1, 6, 0, tzinfo=UTC)
        assert minimal.end is None
        assert minimal.description == ""
        assert minimal.severity is None

    @pytest.mark.asyncio
    async def test_fetch_include_raw(self, instance: PluginInstance) -> None:
        payload = _timeline_payload()
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=payload),
        )
        result = await _fetch(instance, transport, _forecast_params(include_raw=True))

        assert isinstance(result, PluginFetchSuccess)
        assert result.raw == payload

    @pytest.mark.asyncio
    async def test_fetch_request_parameters(self, instance: PluginInstance) -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured["path"] = request.url.path
            captured["unitGroup"] = request.url.params["unitGroup"]
            captured["include"] = request.url.params["include"]
            captured["key"] = request.url.params["key"]
            captured["lang"] = request.url.params["lang"]
            return httpx2.Response(200, json={"days": []})

        transport = httpx2.MockTransport(handler)
        result = await _fetch(instance, transport, _forecast_params(language="de"))

        # An empty payload yields NO_DATA, but the request params are still sent.
        assert isinstance(result, PluginFetchError)
        assert result.code is ErrorCode.NO_DATA
        assert captured["path"].endswith("/timeline/34.0,-117.0")
        assert captured["unitGroup"] == "metric"
        assert captured["include"] == "hours,days,alerts"
        assert captured["key"] == "test-key"
        assert captured["lang"] == "de"

    @pytest.mark.asyncio
    async def test_fetch_custom_include_forwarded(self) -> None:
        config = visual_crossing_plugin.validate_config(
            {"api_key": "test-key", "include": "days"},
        )
        instance = await visual_crossing_plugin.initialize(config)
        captured: dict[str, str] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured["include"] = request.url.params["include"]
            return httpx2.Response(200, json={"days": []})

        result = await _fetch(instance, httpx2.MockTransport(handler))

        assert isinstance(result, PluginFetchError)
        assert result.code is ErrorCode.NO_DATA
        assert captured["include"] == "days"

    @pytest.mark.asyncio
    async def test_fetch_empty_payload_reports_no_data(
        self,
        instance: PluginInstance,
    ) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json={}),
        )
        result = await _fetch(instance, transport)

        # A 200 with no usable forecast content is a NO_DATA error, not a
        # hollow success.
        assert isinstance(result, PluginFetchError)
        assert result.code is ErrorCode.NO_DATA

    @pytest.mark.asyncio
    async def test_fetch_auth_error(self, instance: PluginInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(401, json={"message": "Invalid API key"}),
        )
        result = await _fetch(instance, transport)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.AUTH_FAILED
        assert result.http_status == 401
        assert result.message == "Invalid API key"

    @pytest.mark.asyncio
    async def test_fetch_server_error(self, instance: PluginInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(500, json={"error": "server error"}),
        )
        result = await _fetch(instance, transport)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NETWORK
        assert result.http_status == 500

    @pytest.mark.asyncio
    async def test_fetch_non_dict_payload(self, instance: PluginInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=[{"days": []}]),
        )
        result = await _fetch(instance, transport)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.PARSE
        assert result.message == "Unexpected Visual Crossing payload"
        assert result.raw == [{"days": []}]

    @pytest.mark.asyncio
    async def test_fetch_undecodable_body(self, instance: PluginInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, content=b"not json"),
        )
        result = await _fetch(instance, transport)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.PARSE
        assert result.message.startswith("Could not decode JSON")

    @pytest.mark.asyncio
    async def test_fetch_filters_malformed_rows(
        self,
        instance: PluginInstance,
    ) -> None:
        payload = {
            "days": [
                "corrupt",
                42,
                {
                    # No "datetime": skipped for daily, hours still parsed.
                    "hours": [
                        "corrupt",
                        {"temp": 5.0},  # missing datetimeEpoch -> dropped
                        {"datetimeEpoch": _JAN_2_MIDNIGHT, "temp": 3.5},
                    ],
                },
                {
                    "datetime": "2024-01-01",
                    "tempmax": 20.0,
                    "hours": [],
                },
            ],
            "alerts": [
                "corrupt",
                {"event": "No onset"},  # missing onset time -> dropped
                {"event": "Wind Advisory", "onsetEpoch": _JAN_1_MIDNIGHT},
            ],
        }
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=payload),
        )
        result = await _fetch(instance, transport)

        assert isinstance(result, PluginFetchSuccess)
        forecast = result.forecasts[0]
        assert len(forecast.hourly) == 1
        assert forecast.hourly[0].temperature == 3.5
        assert forecast.hourly[0].is_day is None  # day has no sunrise/sunset epochs
        assert len(forecast.daily) == 1
        assert forecast.daily[0].date == date(2024, 1, 1)
        assert forecast.daily[0].temperature_max == 20.0
        assert len(forecast.alerts) == 1
        assert forecast.alerts[0].event == "Wind Advisory"
        assert forecast.alerts[0].sender_name == "Visual Crossing"

"""Tests for the Google Weather adapter."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from omni_weather_forecast_apis.plugins.google_weather import (
    GoogleWeatherConfig,
    GoogleWeatherInstance,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
    WeatherCondition,
)


def _hour_entry(start: str, temperature: float) -> dict[str, Any]:
    return {
        "interval": {"startTime": start, "endTime": start},
        "isDaytime": True,
        "weatherCondition": {
            "description": {"text": "Partly cloudy", "languageCode": "en"},
            "type": "PARTLY_CLOUDY",
        },
        "temperature": {"degrees": temperature, "unit": "CELSIUS"},
        "feelsLikeTemperature": {"degrees": temperature - 1, "unit": "CELSIUS"},
        "dewPoint": {"degrees": 2.7, "unit": "CELSIUS"},
        "relativeHumidity": 51,
        "uvIndex": 3,
        "precipitation": {
            "probability": {"percent": 40, "type": "RAIN"},
            "qpf": {"quantity": 1.5, "unit": "MILLIMETERS"},
        },
        "airPressure": {"meanSeaLevelMillibars": 1019.13},
        "wind": {
            "direction": {"degrees": 335, "cardinal": "NORTH_NORTHWEST"},
            "speed": {"value": 36, "unit": "KILOMETERS_PER_HOUR"},
            "gust": {"value": 72, "unit": "KILOMETERS_PER_HOUR"},
        },
        "visibility": {"distance": 16, "unit": "KILOMETERS"},
        "cloudCover": 40,
    }


def _day_entry() -> dict[str, Any]:
    return {
        "interval": {
            "startTime": "2026-07-03T15:00:00Z",
            "endTime": "2026-07-04T15:00:00Z",
        },
        "displayDate": {"year": 2026, "month": 7, "day": 3},
        "daytimeForecast": {
            "weatherCondition": {
                "description": {"text": "Scattered showers", "languageCode": "en"},
                "type": "SCATTERED_SHOWERS",
            },
            "relativeHumidity": 54,
            "uvIndex": 6,
            "precipitation": {
                "probability": {"percent": 55, "type": "RAIN"},
                "qpf": {"quantity": 4.0, "unit": "MILLIMETERS"},
            },
            "wind": {
                "direction": {"degrees": 280, "cardinal": "WEST"},
                "speed": {"value": 18, "unit": "KILOMETERS_PER_HOUR"},
                "gust": {"value": 36, "unit": "KILOMETERS_PER_HOUR"},
            },
            "cloudCover": 60,
        },
        "nighttimeForecast": {
            "weatherCondition": {
                "description": {"text": "Partly cloudy", "languageCode": "en"},
                "type": "PARTLY_CLOUDY",
            },
            "relativeHumidity": 86,
            "uvIndex": 0,
            "precipitation": {
                "probability": {"percent": 20, "type": "RAIN"},
                "qpf": {"quantity": 1.0, "unit": "MILLIMETERS"},
            },
            "wind": {
                "direction": {"degrees": 201, "cardinal": "SOUTH_SOUTHWEST"},
                "speed": {"value": 9, "unit": "KILOMETERS_PER_HOUR"},
                "gust": {"value": 18, "unit": "KILOMETERS_PER_HOUR"},
            },
            "cloudCover": 40,
        },
        "maxTemperature": {"degrees": 23.3, "unit": "CELSIUS"},
        "minTemperature": {"degrees": 11.5, "unit": "CELSIUS"},
        "feelsLikeMaxTemperature": {"degrees": 22.0, "unit": "CELSIUS"},
        "feelsLikeMinTemperature": {"degrees": 10.5, "unit": "CELSIUS"},
        "sunEvents": {
            "sunriseTime": "2026-07-03T12:50:00Z",
            "sunsetTime": "2026-07-04T03:30:00Z",
        },
        "moonEvents": {
            "moonPhase": "FULL_MOON",
            "moonriseTimes": ["2026-07-04T04:10:00Z"],
            "moonsetTimes": ["2026-07-03T13:20:00Z"],
        },
    }


def _instance() -> GoogleWeatherInstance:
    return GoogleWeatherInstance(GoogleWeatherConfig(api_key="test-key", hours=48))


def _params(granularity: list[Granularity]) -> PluginFetchParams:
    return PluginFetchParams(
        latitude=37.422,
        longitude=-122.084,
        granularity=granularity,
    )


@pytest.mark.asyncio
async def test_fetch_hourly_normalizes_units_and_conditions() -> None:
    payload = {
        "forecastHours": [_hour_entry("2026-07-03T15:00:00Z", 25.9)],
        "timeZone": {"id": "America/Los_Angeles"},
    }
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))

    async with httpx.AsyncClient(transport=transport) as client:
        result = await _instance().fetch_forecast(
            _params([Granularity.HOURLY]),
            client,
        )

    assert isinstance(result, PluginFetchSuccess)
    point = result.forecasts[0].hourly[0]
    assert point.temperature == 25.9
    assert point.apparent_temperature == 24.9
    assert point.wind_speed == pytest.approx(10.0)  # 36 km/h -> m/s
    assert point.wind_gust == pytest.approx(20.0)
    assert point.wind_direction == 335
    assert point.pressure_sea == pytest.approx(1019.13)
    assert point.precipitation == 1.5
    assert point.precipitation_probability == pytest.approx(0.4)
    assert point.humidity == 51
    assert point.cloud_cover == 40
    assert point.visibility == 16
    assert point.uv_index == 3
    assert point.condition == WeatherCondition.PARTLY_CLOUDY
    assert point.condition_code_original == "PARTLY_CLOUDY"
    assert point.is_day is True


@pytest.mark.asyncio
async def test_fetch_hourly_follows_pagination() -> None:
    pages = {
        None: {
            "forecastHours": [_hour_entry("2026-07-03T15:00:00Z", 20.0)],
            "nextPageToken": "page-two",
        },
        "page-two": {
            "forecastHours": [_hour_entry("2026-07-03T16:00:00Z", 21.0)],
        },
    }
    seen_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("pageToken")
        seen_tokens.append(token)
        return httpx.Response(200, json=pages[token])

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        result = await _instance().fetch_forecast(
            _params([Granularity.HOURLY]),
            client,
        )

    assert isinstance(result, PluginFetchSuccess)
    assert seen_tokens == [None, "page-two"]
    hourly = result.forecasts[0].hourly
    assert [point.temperature for point in hourly] == [20.0, 21.0]


@pytest.mark.asyncio
async def test_fetch_daily_aggregates_day_and_night_parts() -> None:
    payload = {
        "forecastDays": [_day_entry()],
        "timeZone": {"id": "America/Los_Angeles"},
    }
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))

    async with httpx.AsyncClient(transport=transport) as client:
        result = await _instance().fetch_forecast(
            _params([Granularity.DAILY]),
            client,
        )

    assert isinstance(result, PluginFetchSuccess)
    day = result.forecasts[0].daily[0]
    assert day.date.isoformat() == "2026-07-03"
    assert day.temperature_max == 23.3
    assert day.temperature_min == 11.5
    assert day.precipitation_sum == pytest.approx(5.0)
    assert day.precipitation_probability_max == pytest.approx(0.55)
    assert day.wind_speed_max == pytest.approx(5.0)  # 18 km/h -> m/s
    assert day.wind_gust_max == pytest.approx(10.0)
    assert day.humidity_mean == pytest.approx(70.0)
    assert day.cloud_cover_mean == pytest.approx(50.0)
    assert day.uv_index_max == 6
    assert day.condition == WeatherCondition.LIGHT_RAIN
    assert day.summary == "Scattered showers"
    assert day.moon_phase == 0.5
    assert day.sunrise is not None
    assert day.moonrise is not None


@pytest.mark.asyncio
async def test_request_parameters_are_sent() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"forecastHours": []})

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        result = await _instance().fetch_forecast(
            _params([Granularity.HOURLY]),
            client,
        )

    assert isinstance(result, PluginFetchSuccess)
    params = captured[0].url.params
    assert params["key"] == "test-key"
    assert params["location.latitude"] == "37.422"
    assert params["location.longitude"] == "-122.084"
    assert params["unitsSystem"] == "METRIC"
    assert params["hours"] == "48"
    assert params["pageSize"] == "24"


@pytest.mark.asyncio
async def test_http_error_maps_to_fetch_error() -> None:
    error_payload = {"error": {"code": 403, "message": "API key invalid"}}
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            403,
            content=json.dumps(error_payload).encode(),
            headers={"Content-Type": "application/json"},
        ),
    )

    async with httpx.AsyncClient(transport=transport) as client:
        result = await _instance().fetch_forecast(
            _params([Granularity.HOURLY]),
            client,
        )

    assert isinstance(result, PluginFetchError)
    assert result.code == ErrorCode.AUTH_FAILED
    assert result.http_status == 403


def test_config_requires_api_key() -> None:
    with pytest.raises(ValueError, match="api_key"):
        GoogleWeatherConfig.model_validate({})

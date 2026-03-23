"""Tests for Meteosource provider parsing."""

import httpx
import pytest

from omni_weather_forecast_apis.plugins.meteosource import (
    MeteosourceConfig,
    _MeteosourceInstance,
)
from omni_weather_forecast_apis.types import (
    Granularity,
    PluginFetchParams,
    PluginFetchSuccess,
    WeatherCondition,
)


@pytest.mark.asyncio
async def test_fetch_parses_section_data_and_nested_daily_rows() -> None:
    instance = _MeteosourceInstance(
        MeteosourceConfig(
            api_key="test-key",
            sections=["minutely", "hourly", "daily", "alerts"],
        ),
    )
    payload = {
        "minutely": {
            "data": [
                {
                    "date": "2024-01-01T00:00:00Z",
                    "precipitation": {"total": 0.2},
                    "probability": {"precipitation": 40},
                },
                {
                    "date": "bad",
                },
            ],
        },
        "hourly": {
            "data": [
                {
                    "date": "2024-01-01T01:00:00Z",
                    "temperature": 10.0,
                    "weather": {
                        "summary": "Cloudy",
                        "icon": 3,
                    },
                    "wind": {
                        "speed": 4.0,
                        "gust": 7.0,
                        "angle": 90,
                    },
                    "precipitation": {
                        "total": 1.5,
                        "rain": 1.2,
                    },
                    "probability": {
                        "precipitation": 80,
                    },
                    "cloud_cover": {
                        "total": 65,
                    },
                    "visibility": 9.0,
                    "is_day": "0",
                },
                {
                    "date": "bad",
                },
            ],
        },
        "daily": {
            "data": [
                {
                    "day": "2024-01-01",
                    "all_day": {
                        "temperature_max": 14.0,
                        "temperature_min": 6.0,
                        "wind": {},
                        "precipitation": {},
                        "probability": {},
                        "cloud_cover": {},
                    },
                    "summary": "Light rain",
                    "icon": 6,
                    "wind": {
                        "speed": 5.0,
                        "gust": 8.0,
                        "angle": 180,
                    },
                    "precipitation": {
                        "total": 8.0,
                        "rain": 7.0,
                    },
                    "probability": {
                        "precipitation": 60,
                    },
                    "cloud_cover": {
                        "total": 70,
                    },
                    "visibility": 10.0,
                    "humidity": 80,
                    "pressure": 1015,
                    "uv_index": 3.0,
                    "astro": {
                        "sun": {
                            "rise": "2024-01-01T07:00:00Z",
                            "set": "2024-01-01T17:00:00Z",
                        },
                        "moon": {
                            "rise": "2024-01-01T20:00:00Z",
                            "set": "2024-01-01T08:00:00Z",
                            "phase": 0.5,
                        },
                    },
                },
                {
                    "day": "bad",
                },
            ],
        },
        "alerts": {
            "data": [
                {
                    "source": "Meteosource",
                    "event": "Wind Advisory",
                    "start": "2024-01-01T00:00:00Z",
                    "description": "Strong winds",
                    "url": "https://example.com/alert",
                },
                {
                    "event": "Broken alert",
                },
            ],
        },
    }

    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await instance.fetch_forecast(
            PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[
                    Granularity.MINUTELY,
                    Granularity.HOURLY,
                    Granularity.DAILY,
                ],
            ),
            client,
        )

    assert isinstance(result, PluginFetchSuccess)
    forecast = result.forecasts[0]
    assert len(forecast.minutely) == 1
    assert len(forecast.hourly) == 1
    assert len(forecast.daily) == 1
    assert len(forecast.alerts) == 1
    assert forecast.hourly[0].condition == WeatherCondition.OVERCAST
    assert forecast.hourly[0].rain == 1.2
    assert forecast.hourly[0].is_day is False
    assert forecast.daily[0].condition == WeatherCondition.RAIN
    assert forecast.daily[0].precipitation_sum == 8.0
    assert forecast.daily[0].rain_sum == 7.0
    assert forecast.daily[0].cloud_cover_mean == 70.0
    assert forecast.daily[0].pressure_sea_mean == 1015.0

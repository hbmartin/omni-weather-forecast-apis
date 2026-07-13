"""Tests for Pirate Weather provider parsing."""

from datetime import date

import httpx2
import pytest

from omni_weather_forecast_apis.plugins.pirate_weather import (
    PirateWeatherConfig,
    PirateWeatherInstance,
)
from omni_weather_forecast_apis.types import (
    Granularity,
    PluginFetchParams,
    PluginFetchSuccess,
)


@pytest.mark.asyncio
async def test_fetch_preserves_zero_precip_and_skips_alerts_without_start() -> None:
    instance = PirateWeatherInstance(PirateWeatherConfig(api_key="test-key"))
    payload = {
        "hourly": {
            "data": [
                {
                    "time": 1704067200,
                    "temperature": 1.0,
                    "liquidAccumulation": 0.0,
                    "snowAccumulation": 0.5,
                    "precipIntensity": 0.4,
                    "precipType": "snow",
                    "weatherCode": 71,
                },
                {
                    "time": 1704070800,
                    "temperature": 4.0,
                    "precipAccumulation": 0.2,
                    "precipIntensity": 2.0,
                    "precipType": "rain",
                    "weatherCode": 61,
                },
            ],
        },
        "alerts": [
            {
                "title": "Broken alert",
            },
            {
                "title": "Winter Weather Advisory",
                "time": 1704067200,
                "description": "Snow expected",
            },
        ],
    }

    transport = httpx2.MockTransport(
        lambda _request: httpx2.Response(200, json=payload)
    )
    async with httpx2.AsyncClient(transport=transport) as client:
        result = await instance.fetch_forecast(
            PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            ),
            client,
        )

    assert isinstance(result, PluginFetchSuccess)
    forecast = result.forecasts[0]
    snow_hour = forecast.hourly[0]
    # A zero liquid amount is preserved, and the mm/h intensity rate never
    # leaks into the accumulation field.
    assert snow_hour.precipitation == 0.0
    assert snow_hour.rain == 0.0
    # SI accumulations arrive in centimetres; the schema stores millimetres.
    assert snow_hour.snowfall_depth == 5.0
    assert snow_hour.snow is None

    rain_hour = forecast.hourly[1]
    # Without liquidAccumulation, rain-typed precipAccumulation (cm) is the
    # liquid amount; 0.2 cm -> 2.0 mm.
    assert rain_hour.precipitation == 2.0
    assert rain_hour.snowfall_depth is None

    assert len(forecast.alerts) == 1
    assert forecast.alerts[0].event == "Winter Weather Advisory"


@pytest.mark.asyncio
async def test_daily_dates_use_payload_offset() -> None:
    instance = PirateWeatherInstance(PirateWeatherConfig(api_key="test-key"))
    # 2024-01-01 00:00 local midnight at UTC+2 == 2023-12-31 22:00 UTC; the
    # UTC calendar date would be off by one day.
    payload = {
        "offset": 2,
        "daily": {
            "data": [
                {
                    "time": 1704060000,
                    "temperatureHigh": 5.0,
                    "liquidAccumulation": 0.13,
                    "snowAccumulation": 1.0,
                },
            ],
        },
    }

    transport = httpx2.MockTransport(
        lambda _request: httpx2.Response(200, json=payload)
    )
    async with httpx2.AsyncClient(transport=transport) as client:
        result = await instance.fetch_forecast(
            PluginFetchParams(
                latitude=52.0,
                longitude=21.0,
                granularity=[Granularity.DAILY],
            ),
            client,
        )

    assert isinstance(result, PluginFetchSuccess)
    day = result.forecasts[0].daily[0]
    assert day.date == date(2024, 1, 1)
    assert day.precipitation_sum == 1.3
    assert day.snowfall_depth_sum == 10.0
    assert day.snowfall_sum is None

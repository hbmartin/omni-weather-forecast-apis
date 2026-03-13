"""Tests for Weather Unlocked parsing regressions."""

import httpx
import pytest

from omni_weather_forecast_apis.plugins.weather_unlocked import WeatherUnlockedInstance
from omni_weather_forecast_apis.types import (
    Granularity,
    PluginFetchParams,
    PluginFetchSuccess,
    WeatherUnlockedConfig,
)


@pytest.mark.asyncio
async def test_fetch_skips_invalid_hourly_times_and_ignores_blank_sunrise() -> None:
    instance = WeatherUnlockedInstance(
        WeatherUnlockedConfig(app_id="test-id", app_key="test-key"),
    )
    payload = {
        "Days": [
            {
                "date": "2024-01-01",
                "wx_desc": "Cloudy",
                "sunrise_time": "",
                "sunset_time": "1830",
                "Timeframes": [
                    {
                        "time": "bad",
                        "temp_c": 10.0,
                    },
                    {
                        "time": "0600",
                        "temp_c": 9.0,
                        "wx_desc": "Cloudy",
                    },
                ],
            },
        ],
    }

    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await instance.fetch_forecast(
            PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY, Granularity.DAILY],
            ),
            client,
        )

    assert isinstance(result, PluginFetchSuccess)
    forecast = result.forecasts[0]
    assert len(forecast.hourly) == 1
    assert forecast.hourly[0].temperature == 9.0
    assert len(forecast.daily) == 1
    assert forecast.daily[0].sunrise is None
    assert forecast.daily[0].sunset is not None

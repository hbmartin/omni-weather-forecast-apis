"""Tests for Pirate Weather provider parsing."""

import httpx
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
                    "precipAccumulation": 0.0,
                    "precipIntensity": 0.4,
                    "precipType": "snow",
                    "weatherCode": 71,
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

    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
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
    forecast = result.forecasts[0]
    assert forecast.hourly[0].precipitation == 0.0
    assert forecast.hourly[0].rain is None
    assert len(forecast.alerts) == 1
    assert forecast.alerts[0].event == "Winter Weather Advisory"

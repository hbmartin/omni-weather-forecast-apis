"""Tests for Tomorrow.io plugin parsing edge cases."""

import httpx
import pytest

from omni_weather_forecast_apis.plugins.tomorrow_io import _TomorrowIOInstance
from omni_weather_forecast_apis.types import (
    Granularity,
    PluginFetchParams,
    PluginFetchSuccess,
    TomorrowIOConfig,
)


@pytest.mark.asyncio
async def test_fetch_handles_timeline_aliases_and_daily_accumulations() -> None:
    instance = _TomorrowIOInstance(TomorrowIOConfig(api_key="test-key"))
    payload = {
        "timelines": [
            {
                "timestep": "1d",
                "intervals": None,
            },
            {
                "name": "minutely",
                "intervals": [
                    {
                        "startTime": "2024-01-01T00:00:00Z",
                        "values": {
                            "precipitationIntensity": 0.2,
                            "precipitationProbability": 50,
                        },
                    },
                ],
            },
            {
                "name": "hourly",
                "intervals": [
                    {
                        "startTime": "2024-01-01T01:00:00Z",
                        "values": {
                            "temperature": 12.0,
                            "weatherCode": 1000,
                        },
                    },
                ],
            },
            {
                "name": "daily",
                "intervals": [
                    {
                        "startTime": "2024-01-01T00:00:00-08:00",
                        "values": {
                            "temperatureMax": 15.0,
                            "temperatureMin": 5.0,
                            "weatherCodeFullDay": 4001,
                            "precipitationIntensityAvg": 999.0,
                            "rainAccumulation": 2.5,
                            "snowAccumulation": 1.0,
                        },
                    },
                    {
                        "startTime": "not-a-date",
                        "values": {
                            "temperatureMax": 99.0,
                        },
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
    assert forecast.daily[0].date.isoformat() == "2024-01-01"
    assert forecast.daily[0].precipitation_sum == 3.5

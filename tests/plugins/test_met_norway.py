"""Tests for MET Norway parsing regressions."""

import httpx
import pytest

from omni_weather_forecast_apis.plugins.met_norway import (
    METNorwayConfig,
    METNorwayInstance,
)
from omni_weather_forecast_apis.types import (
    Granularity,
    PluginFetchParams,
    PluginFetchSuccess,
)


@pytest.mark.asyncio
async def test_fetch_does_not_use_aggregated_summary_blocks_for_hourly_points() -> None:
    instance = METNorwayInstance(
        METNorwayConfig(user_agent="TestSuite/1.0 test@example.com"),
    )
    payload = {
        "properties": {
            "timeseries": [
                {
                    "time": "2024-01-01T00:00:00Z",
                    "data": {
                        "instant": {
                            "details": {
                                "air_temperature": 3.5,
                                "relative_humidity": 80,
                            },
                        },
                        "next_6_hours": {
                            "summary": {"symbol_code": "lightrain"},
                            "details": {"precipitation_amount": 6.0},
                        },
                    },
                },
            ],
        },
    }
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))

    async with httpx.AsyncClient(transport=transport) as client:
        result = await instance.fetch_forecast(
            PluginFetchParams(
                latitude=60.0,
                longitude=10.0,
                granularity=[Granularity.HOURLY],
            ),
            client,
        )

    assert isinstance(result, PluginFetchSuccess)
    forecast = result.forecasts[0]
    assert len(forecast.hourly) == 1
    assert forecast.hourly[0].temperature == 3.5
    assert forecast.hourly[0].precipitation is None
    assert forecast.hourly[0].condition is None

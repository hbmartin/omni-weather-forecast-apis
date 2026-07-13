"""Tests for Weather Unlocked parsing regressions."""

from datetime import UTC, datetime

import httpx2
import pytest

from omni_weather_forecast_apis.plugins.weather_unlocked import (
    WeatherUnlockedConfig,
    WeatherUnlockedInstance,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
)


def _routing_transport(
    payload: dict,
    *,
    utc_offset_seconds: float | None = -28800,
) -> httpx2.MockTransport:
    """Serve the forecast payload and the Open-Meteo timezone lookup."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "api.open-meteo.com":
            if utc_offset_seconds is None:
                return httpx2.Response(200, json={})
            return httpx2.Response(
                200,
                json={"utc_offset_seconds": utc_offset_seconds},
            )
        return httpx2.Response(200, json=payload)

    return httpx2.MockTransport(handler)


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

    transport = _routing_transport(payload)
    async with httpx2.AsyncClient(transport=transport) as client:
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
    # Regression: 06:00 local at UTC-8 is 14:00 UTC; the naive local string
    # used to be stored as 06:00 UTC.
    assert forecast.hourly[0].timestamp == datetime(2024, 1, 1, 14, 0, tzinfo=UTC)
    assert len(forecast.daily) == 1
    assert forecast.daily[0].sunrise is None
    sunset = forecast.daily[0].sunset
    assert sunset == datetime(2024, 1, 2, 2, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_fetch_fails_when_timezone_lookup_is_unusable() -> None:
    instance = WeatherUnlockedInstance(
        WeatherUnlockedConfig(app_id="test-id", app_key="test-key"),
    )
    payload = {"Days": []}

    transport = _routing_transport(payload, utc_offset_seconds=None)
    async with httpx2.AsyncClient(transport=transport) as client:
        result = await instance.fetch_forecast(
            PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            ),
            client,
        )

    # Failing loudly beats silently storing local times as UTC.
    assert isinstance(result, PluginFetchError)
    assert result.code == ErrorCode.PARSE

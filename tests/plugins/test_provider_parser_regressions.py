"""Regression tests for provider-specific parser fixes."""

import httpx
import pytest

from omni_weather_forecast_apis.plugins.meteosource import (
    MeteosourceConfig,
    _MeteosourceInstance,
)
from omni_weather_forecast_apis.plugins.tomorrow_io import (
    TomorrowIOConfig,
    _TomorrowIOInstance,
)
from omni_weather_forecast_apis.types import (
    Granularity,
    PluginFetchParams,
    PluginFetchSuccess,
)


@pytest.mark.asyncio
async def test_meteosource_parses_data_sections_and_nested_fields() -> None:
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
                    "precipitation": {"total": 0.25},
                    "probability": {"precipitation": 20},
                },
            ],
        },
        "hourly": {
            "data": [
                {
                    "date": "2024-01-01T01:00:00Z",
                    "summary": "Partly cloudy",
                    "icon_num": 2,
                    "temperature": 10.0,
                    "wind": {"speed": 4.0, "gust": 8.0, "angle": 270},
                    "precipitation": {"total": 1.5, "rain": 1.0},
                    "probability": {"precipitation": 40},
                    "cloud_cover": {"total": 70},
                    "visibility": 12.0,
                    "uv_index": 1.0,
                    "is_day": 1,
                },
            ],
        },
        "daily": {
            "data": [
                {
                    "day": "2024-01-02",
                    "all_day": {
                        "summary": "Rain",
                        "icon": 6,
                        "temperature_max": 14.0,
                        "temperature_min": 7.0,
                        "wind": {"speed": 6.0, "gust": 10.0, "angle": 180},
                        "precipitation": {"total": 5.5, "rain": 5.0, "snow": 0.5},
                        "probability": {"precipitation": 60},
                        "cloud_cover": {"total": 80},
                        "uv_index": 3.0,
                        "humidity": 65,
                    },
                    "astro": {
                        "sun": {
                            "rise": "2024-01-02T07:01:00Z",
                            "set": "2024-01-02T17:02:00Z",
                        },
                        "moon": {
                            "rise": "2024-01-02T20:00:00Z",
                            "set": "2024-01-03T08:00:00Z",
                            "phase": 0.4,
                        },
                    },
                },
            ],
        },
        "alerts": [
            {
                "start": "2024-01-01T00:00:00Z",
                "event": "Wind Advisory",
                "description": "Test alert",
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
    assert forecast.minutely[0].precipitation_intensity == 0.25
    assert len(forecast.hourly) == 1
    assert forecast.hourly[0].wind_speed == 4.0
    assert forecast.hourly[0].precipitation_probability == 0.4
    assert forecast.hourly[0].cloud_cover == 70.0
    assert len(forecast.daily) == 1
    assert forecast.daily[0].precipitation_sum == 5.5
    assert forecast.daily[0].rain_sum == 5.0
    assert forecast.daily[0].snowfall_sum == 0.5
    assert forecast.daily[0].sunrise is not None
    assert len(forecast.alerts) == 1


@pytest.mark.asyncio
async def test_meteosource_skips_bad_rows_without_failing_provider() -> None:
    instance = _MeteosourceInstance(MeteosourceConfig(api_key="test-key"))
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"hourly": {"data": [{"date": "not-a-timestamp"}]}},
        ),
    )

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
    assert result.forecasts[0].hourly == []


@pytest.mark.asyncio
async def test_tomorrow_io_parses_forecast_timelines_and_daily_totals() -> None:
    instance = _TomorrowIOInstance(TomorrowIOConfig(api_key="test-key"))
    payload = {
        "timelines": {
            "minutely": [
                {
                    "startTime": "2024-01-01T00:00:00Z",
                    "values": {
                        "precipitationIntensity": 0.1,
                        "precipitationProbability": 20,
                    },
                },
            ],
            "hourly": [
                {
                    "startTime": "2024-01-01T01:00:00Z",
                    "values": {
                        "temperature": 11.0,
                        "weatherCode": 1000,
                        "isDay": True,
                    },
                },
            ],
            "daily": [
                {
                    "startTime": "2024-01-02T00:00:00-08:00",
                    "values": {
                        "temperatureMax": 15.0,
                        "temperatureMin": 7.0,
                        "weatherCodeFullDay": 4001,
                        "rainAccumulationSum": 2.5,
                        "snowAccumulationSum": 1.0,
                        "sleetAccumulationSum": 0.5,
                        "precipitationProbabilityMax": 30,
                    },
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
    assert forecast.minutely[0].precipitation_probability == 0.2
    assert len(forecast.hourly) == 1
    assert forecast.hourly[0].temperature == 11.0
    assert len(forecast.daily) == 1
    assert forecast.daily[0].date.isoformat() == "2024-01-02"
    assert forecast.daily[0].precipitation_sum == 4.0
    assert forecast.daily[0].rain_sum == 2.5
    assert forecast.daily[0].snowfall_sum == 1.0


@pytest.mark.asyncio
async def test_tomorrow_io_ignores_null_intervals() -> None:
    instance = _TomorrowIOInstance(TomorrowIOConfig(api_key="test-key"))
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"timelines": [{"timestep": "1h", "intervals": None}]},
        ),
    )

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
    assert result.forecasts[0].hourly == []

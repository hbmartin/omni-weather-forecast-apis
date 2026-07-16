"""Tests for the NWS provider."""

import httpx2
import pytest
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.nws import (
    NWSGridOverride,
    _alert_url,
    _dew_point,
    _humidity,
    _local_start_date,
    nws_plugin,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    PluginFetchParams,
)


def test_local_start_date_rejects_boolean_values() -> None:
    assert _local_start_date({"startTime": True}) is None


def test_alert_url_strips_whitespace() -> None:
    assert _alert_url({"id": "  https://example.com/alert  "}, {}) == (
        "https://example.com/alert"
    )


def test_humidity_reads_relative_humidity_value() -> None:
    assert _humidity(
        {"relativeHumidity": {"value": 62, "unitCode": "wmoUnit:percent"}},
    ) == pytest.approx(62)
    assert _humidity({"relativeHumidity": {"value": None}}) is None
    assert _humidity({}) is None


def test_dew_point_reads_celsius_and_converts_fahrenheit() -> None:
    assert _dew_point(
        {"dewpoint": {"value": 12.5, "unitCode": "wmoUnit:degC"}},
    ) == pytest.approx(12.5)
    # 50 °F -> 10 °C when the unit code marks Fahrenheit.
    assert _dew_point(
        {"dewpoint": {"value": 50, "unitCode": "wmoUnit:degF"}},
    ) == pytest.approx(10.0)
    assert _dew_point({"dewpoint": {"value": None}}) is None
    assert _dew_point({}) is None


def test_grid_override_rejects_empty_office() -> None:
    with pytest.raises(ValidationError):
        NWSGridOverride(office="", grid_x=1, grid_y=2)


@pytest.mark.asyncio
async def test_fetch_forecast_normalizes_all_nws_endpoints() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        match request.url.path:
            case "/points/34.0,-118.0":
                payload = {
                    "properties": {
                        "forecast": "https://api.weather.gov/gridpoints/LOX/154,44/forecast",
                        "forecastHourly": "https://api.weather.gov/gridpoints/LOX/154,44/forecast/hourly",
                        "timeZone": "America/Los_Angeles",
                    },
                }
            case "/gridpoints/LOX/154,44/forecast/hourly":
                payload = {
                    "properties": {
                        "periods": [
                            {
                                "startTime": "2026-07-12T10:00:00-07:00",
                                "temperature": 68,
                                "temperatureUnit": "F",
                                "probabilityOfPrecipitation": {"value": 30},
                                "relativeHumidity": {
                                    "value": 55,
                                    "unitCode": "wmoUnit:percent",
                                },
                                "dewpoint": {
                                    "value": 12.5,
                                    "unitCode": "wmoUnit:degC",
                                },
                                "windSpeed": "5 to 15 mph",
                                "windDirection": "NW",
                                "shortForecast": "Chance Rain",
                                "isDaytime": True,
                            },
                            {"temperature": 70},
                        ],
                    },
                }
            case "/gridpoints/LOX/154,44/forecast":
                payload = {
                    "properties": {
                        "periods": [
                            {
                                "startTime": "2026-07-12T06:00:00-07:00",
                                "temperature": 77,
                                "temperatureUnit": "F",
                                "windSpeed": "10 mph",
                                "windDirection": "S",
                                "shortForecast": "Sunny",
                                "detailedForecast": "Sunny and warm.",
                                "isDaytime": True,
                            },
                            {
                                "startTime": "2026-07-12T18:00:00-07:00",
                                "temperature": 59,
                                "temperatureUnit": "F",
                                "shortForecast": "Clear",
                                "isDaytime": False,
                            },
                        ],
                    },
                }
            case "/alerts/active":
                assert request.url.params["point"] == "34.0,-118.0"
                payload = {
                    "features": [
                        {
                            "id": "https://api.weather.gov/alerts/123",
                            "properties": {
                                "senderName": "NWS Los Angeles",
                                "event": "Heat Advisory",
                                "onset": "2026-07-12T12:00:00Z",
                                "ends": "2026-07-13T03:00:00Z",
                                "description": "Hot conditions expected.",
                                "severity": "Moderate",
                            },
                        },
                    ],
                }
            case _:
                return httpx2.Response(404)
        return httpx2.Response(200, json=payload)

    config = nws_plugin.validate_config({"user_agent": "weather-tests@example.com"})
    instance = await nws_plugin.initialize(config)
    params = PluginFetchParams(
        latitude=34,
        longitude=-118,
        granularity=[Granularity.HOURLY, Granularity.DAILY],
        include_raw=True,
    )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        result = await instance.fetch_forecast(params, client)

    assert result.status == "success"
    assert result.raw is not None
    forecast = result.forecasts[0]
    assert forecast.timezone == "America/Los_Angeles"
    assert len(forecast.hourly) == 1
    assert forecast.hourly[0].temperature == pytest.approx(20)
    assert forecast.hourly[0].precipitation_probability == pytest.approx(0.3)
    assert forecast.hourly[0].humidity == pytest.approx(55)
    assert forecast.hourly[0].dew_point == pytest.approx(12.5)
    assert forecast.hourly[0].wind_direction == pytest.approx(315)
    assert len(forecast.daily) == 1
    assert forecast.daily[0].temperature_max == pytest.approx(25)
    assert forecast.daily[0].temperature_min == pytest.approx(15)
    assert forecast.daily[0].summary == "Sunny and warm."
    assert len(forecast.alerts) == 1
    assert forecast.alerts[0].event == "Heat Advisory"
    assert forecast.alerts[0].url == "https://api.weather.gov/alerts/123"
    assert all(
        request.headers["User-Agent"] == "weather-tests@example.com"
        for request in requests
    )


@pytest.mark.asyncio
async def test_fetch_forecast_reports_missing_point_properties() -> None:
    transport = httpx2.MockTransport(
        lambda _request: httpx2.Response(200, json={}),
    )
    config = nws_plugin.validate_config({"user_agent": "weather-tests@example.com"})
    instance = await nws_plugin.initialize(config)
    params = PluginFetchParams(
        latitude=34,
        longitude=-118,
        granularity=[Granularity.HOURLY],
    )

    async with httpx2.AsyncClient(transport=transport) as client:
        result = await instance.fetch_forecast(params, client)

    assert result.status == "error"
    assert result.code is ErrorCode.PARSE
    assert result.message == "NWS points payload missing properties"


@pytest.mark.asyncio
async def test_fetch_forecast_with_only_alerts_still_succeeds() -> None:
    """An alerts-only payload carries usable content and must stay a success."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        match request.url.path:
            case "/gridpoints/LOX/154,44/forecast/hourly":
                return httpx2.Response(200, json={"properties": {"periods": []}})
            case "/gridpoints/LOX/154,44/forecast":
                return httpx2.Response(200, json={"properties": {"periods": []}})
            case "/alerts/active":
                return httpx2.Response(
                    200,
                    json={
                        "features": [
                            {
                                "id": "https://api.weather.gov/alerts/999",
                                "properties": {
                                    "senderName": "NWS Los Angeles",
                                    "event": "Wind Advisory",
                                    "onset": "2026-07-12T12:00:00Z",
                                    "ends": "2026-07-13T03:00:00Z",
                                    "description": "Windy.",
                                    "severity": "Moderate",
                                },
                            },
                        ],
                    },
                )
            case _:
                return httpx2.Response(404)

    config = nws_plugin.validate_config(
        {
            "user_agent": "weather-tests@example.com",
            "grid_override": {"office": "LOX", "grid_x": 154, "grid_y": 44},
        },
    )
    instance = await nws_plugin.initialize(config)
    params = PluginFetchParams(
        latitude=34,
        longitude=-118,
        granularity=[Granularity.HOURLY, Granularity.DAILY],
        timezone="America/Los_Angeles",
    )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        result = await instance.fetch_forecast(params, client)

    assert result.status == "success"
    forecast = result.forecasts[0]
    assert forecast.hourly == []
    assert forecast.daily == []
    assert len(forecast.alerts) == 1
    assert forecast.alerts[0].event == "Wind Advisory"

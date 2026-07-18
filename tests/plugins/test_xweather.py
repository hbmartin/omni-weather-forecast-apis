"""Tests for the Xweather plugin using httpx2 mocks."""

from __future__ import annotations

from datetime import date

import httpx2
import pytest
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.xweather import (
    XweatherConfig,
    XweatherInstance,
    _parse_day,
    xweather_plugin,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
    ProviderId,
    WeatherCondition,
)

HOURLY_PERIOD = {
    "dateTimeISO": "2026-07-18T12:00:00-05:00",
    "timestamp": 1784394000,
    "tempC": 20.5,
    "feelslikeC": 19.8,
    "dewpointC": 11.4,
    "humidity": 62,
    "pop": 60,
    "precipMM": 0.8,
    "snowCM": 2.5,
    "windSpeedKPH": 36,
    "windGustKPH": 54,
    "windDirDEG": 210,
    "sky": 40,
    "uvi": 5,
    "visibilityKM": 16.0,
    "pressureMB": 1015.0,
    "solradWM2": 420,
    "weather": "Light Rain",
    "weatherPrimary": "Light Rain",
    "weatherPrimaryCoded": ":L:R",
    "cloudsCoded": "SC",
    "isDay": True,
}

DAILY_PERIOD = {
    "dateTimeISO": "2026-07-18T00:00:00-05:00",
    "maxTempC": 28.0,
    "minTempC": 17.0,
    "maxFeelslikeC": 29.5,
    "minFeelslikeC": 16.2,
    "maxHumidity": 80,
    "minHumidity": 40,
    "pop": 35,
    "precipMM": 4.2,
    "snowCM": 0,
    "windSpeedMaxKPH": 36,
    "windGustKPH": 72,
    "windDirDEG": 200,
    "sky": 55,
    "uvi": 8,
    "weatherPrimary": "Partly Cloudy",
    "weatherPrimaryCoded": "::",
    "cloudsCoded": "SC",
    "sunriseISO": "2026-07-18T05:58:00-05:00",
    "sunsetISO": "2026-07-18T20:34:00-05:00",
}


def _envelope(periods: list[object]) -> dict[str, object]:
    return {
        "success": True,
        "error": None,
        "response": [
            {
                "loc": {"long": -117.0, "lat": 34.0},
                "periods": periods,
                "profile": {"tz": "America/Chicago"},
            },
        ],
    }


def _fetch_params(
    granularity: list[Granularity] | None = None,
) -> PluginFetchParams:
    return PluginFetchParams(
        latitude=34.0,
        longitude=-117.0,
        granularity=granularity or [Granularity.HOURLY, Granularity.DAILY],
    )


def _instance() -> XweatherInstance:
    return XweatherInstance(
        XweatherConfig(client_id="test-id", client_secret="test-secret"),
    )


class TestXweatherPlugin:
    def test_plugin_id(self) -> None:
        assert xweather_plugin.id == ProviderId.XWEATHER

    def test_validate_config_defaults(self) -> None:
        config = xweather_plugin.validate_config(
            {"client_id": "abc", "client_secret": "def"},
        )
        assert isinstance(config, XweatherConfig)
        assert config.hourly_limit == 120
        assert config.daily_limit == 10

    @pytest.mark.parametrize(
        "config",
        [
            {},
            {"client_id": "abc"},
            {"client_secret": "def"},
            {"client_id": "", "client_secret": "def"},
        ],
    )
    def test_validate_config_rejects_missing_credentials(
        self,
        config: dict[str, str],
    ) -> None:
        with pytest.raises(ValidationError):
            xweather_plugin.validate_config(config)


class TestXweatherInstance:
    def test_capabilities_follow_config(self) -> None:
        instance = XweatherInstance(
            XweatherConfig(
                client_id="a",
                client_secret="b",
                hourly_limit=48,
                daily_limit=7,
            ),
        )
        caps = instance.get_capabilities()
        assert caps.granularity_minutely is False
        assert caps.max_horizon_hourly_hours == 48.0
        assert caps.max_horizon_daily_days == 7.0
        assert caps.alerts is False

    def test_polar_day_omits_false_sunrise_and_sunset(self) -> None:
        period = {
            **DAILY_PERIOD,
            "sunriseISO": False,
            "sunsetISO": False,
        }

        day = _parse_day(period)

        assert day.sunrise is None
        assert day.sunset is None

    @pytest.mark.asyncio
    async def test_fetch_success(self) -> None:
        captured_queries: list[dict[str, str]] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            params = dict(request.url.params)
            captured_queries.append(params)
            assert request.url.path == "/forecasts/34.0,-117.0"
            if params["filter"] == "1hr":
                return httpx2.Response(200, json=_envelope([HOURLY_PERIOD]))
            return httpx2.Response(200, json=_envelope([DAILY_PERIOD]))

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await _instance().fetch_forecast(_fetch_params(), client)

        assert [query["filter"] for query in captured_queries] == ["1hr", "day"]
        assert captured_queries[0]["client_id"] == "test-id"
        assert captured_queries[0]["client_secret"] == "test-secret"
        assert captured_queries[0]["limit"] == "120"
        assert captured_queries[1]["limit"] == "10"

        assert isinstance(result, PluginFetchSuccess)
        forecast = result.forecasts[0]
        assert forecast.source.provider == ProviderId.XWEATHER
        assert forecast.timezone == "America/Chicago"

        point = forecast.hourly[0]
        assert point.temperature == 20.5
        assert point.apparent_temperature == 19.8
        assert point.dew_point == 11.4
        assert point.humidity == 62.0
        assert point.precipitation == 0.8
        assert point.precipitation_probability == 0.6
        assert point.snowfall_depth == 25.0
        assert point.wind_speed == 10.0
        assert point.wind_gust == 15.0
        assert point.wind_direction == 210.0
        assert point.cloud_cover == 40.0
        assert point.uv_index == 5.0
        assert point.visibility == 16.0
        assert point.pressure_sea == 1015.0
        assert point.solar_radiation_ghi == 420.0
        assert point.condition == WeatherCondition.LIGHT_RAIN
        assert point.condition_original == "Light Rain"
        assert point.condition_code_original == ":L:R"
        assert point.is_day is True

        day = forecast.daily[0]
        assert day.date == date(2026, 7, 18)
        assert day.temperature_max == 28.0
        assert day.temperature_min == 17.0
        assert day.apparent_temperature_max == 29.5
        assert day.apparent_temperature_min == 16.2
        assert day.wind_speed_max == 10.0
        assert day.wind_gust_max == 20.0
        assert day.wind_direction_dominant == 200.0
        assert day.precipitation_sum == 4.2
        assert day.precipitation_probability_max == 0.35
        assert day.snowfall_depth_sum == 0.0
        assert day.cloud_cover_mean == 55.0
        assert day.uv_index_max == 8.0
        assert day.humidity_mean == 60.0
        assert day.condition == WeatherCondition.PARTLY_CLOUDY
        assert day.sunrise is not None
        assert day.sunset is not None

    @pytest.mark.asyncio
    async def test_hourly_only_issues_single_request(self) -> None:
        captured_filters: list[str] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured_filters.append(request.url.params["filter"])
            return httpx2.Response(200, json=_envelope([HOURLY_PERIOD]))

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await _instance().fetch_forecast(
                _fetch_params([Granularity.HOURLY]),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert captured_filters == ["1hr"]

    @pytest.mark.asyncio
    async def test_envelope_auth_error_with_http_200(self) -> None:
        payload = {
            "success": False,
            "error": {
                "code": "invalid_client",
                "description": "The client provided is invalid.",
            },
            "response": [],
        }
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=payload),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await _instance().fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.AUTH_FAILED
        assert result.message == "The client provided is invalid."

    @pytest.mark.asyncio
    async def test_envelope_rate_limit_error(self) -> None:
        payload = {
            "success": False,
            "error": {"code": "maxed_out", "description": ""},
            "response": [],
        }
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=payload),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await _instance().fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.RATE_LIMITED
        assert result.message == "Xweather request failed (maxed_out)"

    @pytest.mark.asyncio
    async def test_warn_no_data_yields_no_data(self) -> None:
        payload = {
            "success": False,
            "error": {"code": "warn_no_data", "description": "No data available."},
            "response": [],
        }
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=payload),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await _instance().fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NO_DATA

    @pytest.mark.asyncio
    async def test_fetch_server_error(self) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(500, json={"message": "boom"}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await _instance().fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_invalid_profile_timezone_falls_back_to_params(self) -> None:
        payload = {
            "success": True,
            "error": None,
            "response": [
                {"periods": [HOURLY_PERIOD], "profile": {"tz": "Not/AZone"}},
            ],
        }
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=payload),
        )
        params = PluginFetchParams(
            latitude=34.0,
            longitude=-117.0,
            granularity=[Granularity.HOURLY],
            timezone="America/Los_Angeles",
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await _instance().fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        assert result.forecasts[0].timezone == "America/Los_Angeles"

    @pytest.mark.asyncio
    async def test_non_dict_periods_are_skipped(self) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200,
                json=_envelope(["nope", 3, None, HOURLY_PERIOD]),
            ),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await _instance().fetch_forecast(
                _fetch_params([Granularity.HOURLY]),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts[0].hourly) == 1

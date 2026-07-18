"""Tests for the Apple WeatherKit plugin using httpx2 mocks."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.weatherkit import (
    WeatherKitConfig,
    WeatherKitInstance,
    weatherkit_plugin,
)
from omni_weather_forecast_apis.types import (
    AlertSeverity,
    ErrorCode,
    Granularity,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
    ProviderId,
    WeatherCondition,
)

WEATHER_PAYLOAD = {
    "forecastHourly": {
        "hours": [
            {
                "forecastStart": "2026-07-18T12:00:00Z",
                "temperature": 25.0,
                "temperatureApparent": 26.1,
                "temperatureDewPoint": 10.0,
                "humidity": 0.45,
                "windSpeed": 18.0,
                "windGust": 36.0,
                "windDirection": 270,
                "pressure": 1012.0,
                "precipitationAmount": 0.3,
                "precipitationChance": 0.25,
                "cloudCover": 0.8,
                "visibility": 12000.0,
                "uvIndex": 7,
                "conditionCode": "Thunderstorms",
                "daylight": True,
            },
        ],
    },
    "forecastDaily": {
        "days": [
            {
                "forecastStart": "2026-07-18T07:00:00Z",
                "forecastEnd": "2026-07-19T07:00:00Z",
                "temperatureMax": 28.0,
                "temperatureMin": 15.0,
                "precipitationAmount": 1.5,
                "precipitationChance": 0.3,
                "snowfallAmount": 0.0,
                "maxUvIndex": 8,
                "conditionCode": "MostlyClear",
                "moonPhase": "full",
                "sunrise": "2026-07-18T12:58:00Z",
                "sunset": "2026-07-19T03:04:00Z",
                "daytimeForecast": {
                    "windSpeed": 18.0,
                    "windDirection": 260,
                    "cloudCover": 0.4,
                    "humidity": 0.5,
                    "conditionCode": "PartlyCloudy",
                },
                "overnightForecast": {
                    "windSpeed": 9.0,
                    "cloudCover": 0.2,
                    "humidity": 0.7,
                },
            },
        ],
    },
    "forecastNextHour": {
        "minutes": [
            {
                "startTime": "2026-07-18T12:00:00Z",
                "precipitationChance": 0.1,
                "precipitationIntensity": 0.4,
            },
        ],
    },
    "weatherAlerts": {
        "alerts": [
            {
                "description": "Heat Advisory",
                "source": "National Weather Service",
                "severity": "moderate",
                "effectiveTime": "2026-07-18T10:00:00Z",
                "eventEndTime": "2026-07-19T02:00:00Z",
                "detailsUrl": "https://example.com/alert",
            },
            {"description": "No time alert"},
        ],
    },
}


@pytest.fixture(scope="module")
def private_key_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _config(private_key_pem: str, **overrides: object) -> WeatherKitConfig:
    values: dict[str, object] = {
        "team_id": "TEAM123",
        "service_id": "com.example.weather",
        "key_id": "KEYID789",
        "private_key": private_key_pem,
        **overrides,
    }
    return WeatherKitConfig.model_validate(values)


def _fetch_params(
    granularity: list[Granularity] | None = None,
    timezone: str | None = "America/Los_Angeles",
) -> PluginFetchParams:
    return PluginFetchParams(
        latitude=34.0,
        longitude=-117.0,
        granularity=(
            granularity
            if granularity is not None
            else [Granularity.MINUTELY, Granularity.HOURLY, Granularity.DAILY]
        ),
        timezone=timezone,
    )


class TestWeatherKitConfig:
    def test_plugin_id(self) -> None:
        assert weatherkit_plugin.id == ProviderId.WEATHERKIT

    def test_accepts_inline_private_key(self, private_key_pem: str) -> None:
        config = _config(private_key_pem)
        assert config.private_key == private_key_pem
        assert config.hours == 48

    def test_accepts_private_key_path(
        self,
        private_key_pem: str,
        tmp_path: Path,
    ) -> None:
        key_path = tmp_path / "AuthKey.p8"
        key_path.write_text(private_key_pem)
        config = _config(
            private_key_pem, private_key=None, private_key_path=str(key_path)
        )
        assert config.private_key_path == str(key_path)

    def test_rejects_missing_key_material(self) -> None:
        with pytest.raises(ValidationError):
            _config("ignored", private_key=None)

    def test_rejects_both_key_sources(self, private_key_pem: str) -> None:
        with pytest.raises(ValidationError):
            _config(private_key_pem, private_key_path="unused/AuthKey.p8")

    def test_rejects_blank_team_id(self, private_key_pem: str) -> None:
        with pytest.raises(ValidationError):
            _config(private_key_pem, team_id="")


class TestBearerToken:
    def test_token_headers_and_claims(self, private_key_pem: str) -> None:
        instance = WeatherKitInstance(_config(private_key_pem))
        token = instance._bearer_token(now=1_000_000.0)

        assert isinstance(token, str)
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "ES256"
        assert header["kid"] == "KEYID789"
        assert header["id"] == "TEAM123.com.example.weather"

        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims == {
            "iss": "TEAM123",
            "sub": "com.example.weather",
            "iat": 1_000_000,
            "exp": 1_003_600,
        }

    def test_token_is_cached_until_refresh_margin(self, private_key_pem: str) -> None:
        instance = WeatherKitInstance(_config(private_key_pem))
        first = instance._bearer_token(now=1_000_000.0)
        cached = instance._bearer_token(now=1_002_000.0)
        refreshed = instance._bearer_token(now=1_003_100.0)

        assert first == cached
        assert refreshed != first

    def test_reads_key_from_path(self, private_key_pem: str, tmp_path: Path) -> None:
        key_path = tmp_path / "AuthKey.p8"
        key_path.write_text(private_key_pem)
        instance = WeatherKitInstance(
            _config(private_key_pem, private_key=None, private_key_path=str(key_path)),
        )
        assert isinstance(instance._bearer_token(now=0.0), str)

    def test_missing_key_file_returns_auth_error(self, private_key_pem: str) -> None:
        instance = WeatherKitInstance(
            _config(
                private_key_pem,
                private_key=None,
                private_key_path="/nonexistent/AuthKey.p8",
            ),
        )
        token = instance._bearer_token(now=0.0)
        assert isinstance(token, PluginFetchError)
        assert token.code == ErrorCode.AUTH_FAILED


class TestWeatherKitInstance:
    def test_capabilities(self, private_key_pem: str) -> None:
        instance = WeatherKitInstance(_config(private_key_pem, hours=120))
        caps = instance.get_capabilities()
        assert caps.granularity_minutely is True
        assert caps.granularity_hourly is True
        assert caps.granularity_daily is True
        assert caps.max_horizon_minutely_hours == 1
        assert caps.max_horizon_hourly_hours == 120.0
        assert caps.max_horizon_daily_days == 10
        assert caps.alerts is True

    @pytest.mark.asyncio
    async def test_invalid_key_fails_before_any_request(self) -> None:
        instance = WeatherKitInstance(
            WeatherKitConfig(
                team_id="TEAM123",
                service_id="com.example.weather",
                key_id="KEYID789",
                private_key="not a pem",
            ),
        )
        requests_seen: list[str] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            requests_seen.append(str(request.url))
            return httpx2.Response(200, json={})

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.AUTH_FAILED
        assert requests_seen == []

    @pytest.mark.asyncio
    async def test_fetch_success(self, private_key_pem: str) -> None:
        instance = WeatherKitInstance(_config(private_key_pem, country_code="US"))
        captured: dict[str, object] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured["path"] = request.url.path
            captured["params"] = dict(request.url.params)
            captured["authorization"] = request.headers["Authorization"]
            return httpx2.Response(200, json=WEATHER_PAYLOAD)

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert captured["path"] == "/api/v1/weather/en/34.0/-117.0"
        params = captured["params"]
        assert isinstance(params, dict)
        assert (
            params["dataSets"]
            == "forecastNextHour,forecastHourly,forecastDaily,weatherAlerts"
        )
        assert params["timezone"] == "America/Los_Angeles"
        assert params["countryCode"] == "US"
        assert "hourlyEnd" in params
        authorization = captured["authorization"]
        assert isinstance(authorization, str)
        assert authorization.startswith("Bearer ")

        assert isinstance(result, PluginFetchSuccess)
        forecast = result.forecasts[0]
        assert forecast.source.provider == ProviderId.WEATHERKIT
        assert forecast.timezone == "America/Los_Angeles"

        point = forecast.hourly[0]
        assert point.timestamp == datetime(2026, 7, 18, 12, tzinfo=UTC)
        assert point.temperature == 25.0
        assert point.apparent_temperature == 26.1
        assert point.dew_point == 10.0
        assert point.humidity == 45.0
        assert point.wind_speed == 5.0
        assert point.wind_gust == 10.0
        assert point.wind_direction == 270.0
        assert point.pressure_sea == 1012.0
        assert point.precipitation == 0.3
        assert point.precipitation_probability == 0.25
        assert point.cloud_cover == 80.0
        assert point.visibility == 12.0
        assert point.uv_index == 7.0
        assert point.condition == WeatherCondition.THUNDERSTORM
        assert point.condition_code_original == "Thunderstorms"
        assert point.is_day is True

        day = forecast.daily[0]
        assert day.date == date(2026, 7, 18)
        assert day.temperature_max == 28.0
        assert day.temperature_min == 15.0
        assert day.wind_speed_max == 5.0
        assert day.wind_direction_dominant == 260.0
        assert day.precipitation_sum == 1.5
        assert day.precipitation_probability_max == 0.3
        assert day.snowfall_depth_sum == 0.0
        assert day.cloud_cover_mean == 30.0
        assert day.uv_index_max == 8.0
        assert day.humidity_mean == 60.0
        assert day.condition == WeatherCondition.MOSTLY_CLEAR
        assert day.moon_phase == 0.5
        assert day.sunrise is not None

        minute = forecast.minutely[0]
        assert minute.precipitation_intensity == 0.4
        assert minute.precipitation_probability == 0.1

        assert len(forecast.alerts) == 1
        alert = forecast.alerts[0]
        assert alert.sender_name == "National Weather Service"
        assert alert.event == "Heat Advisory"
        assert alert.severity == AlertSeverity.MODERATE
        assert alert.url == "https://example.com/alert"

    @pytest.mark.asyncio
    async def test_no_country_code_omits_alerts_data_set(
        self,
        private_key_pem: str,
    ) -> None:
        instance = WeatherKitInstance(_config(private_key_pem))
        captured_params: dict[str, str] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured_params.update(dict(request.url.params))
            return httpx2.Response(200, json=WEATHER_PAYLOAD)

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params([Granularity.HOURLY]),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert captured_params["dataSets"] == "forecastHourly"
        assert "countryCode" not in captured_params

    @pytest.mark.asyncio
    async def test_no_requested_granularity_yields_no_data(
        self,
        private_key_pem: str,
    ) -> None:
        instance = WeatherKitInstance(_config(private_key_pem))
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=WEATHER_PAYLOAD),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params([]), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NO_DATA

    @pytest.mark.asyncio
    async def test_missing_next_hour_section_still_succeeds(
        self,
        private_key_pem: str,
    ) -> None:
        instance = WeatherKitInstance(_config(private_key_pem))
        payload = {"forecastHourly": WEATHER_PAYLOAD["forecastHourly"]}
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=payload),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchSuccess)
        forecast = result.forecasts[0]
        assert forecast.minutely == []
        assert len(forecast.hourly) == 1

    @pytest.mark.asyncio
    async def test_resolves_timezone_via_lookup_when_missing(
        self,
        private_key_pem: str,
    ) -> None:
        instance = WeatherKitInstance(_config(private_key_pem))

        def handler(request: httpx2.Request) -> httpx2.Response:
            if request.url.host == "api.open-meteo.com":
                return httpx2.Response(200, json={"timezone": "America/Los_Angeles"})
            return httpx2.Response(200, json=WEATHER_PAYLOAD)

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                _fetch_params(timezone=None),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert result.forecasts[0].timezone == "America/Los_Angeles"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [401, 403])
    async def test_fetch_auth_error(
        self,
        private_key_pem: str,
        status_code: int,
    ) -> None:
        instance = WeatherKitInstance(_config(private_key_pem))
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(status_code, json={}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.AUTH_FAILED
        assert result.http_status == status_code

    @pytest.mark.asyncio
    async def test_fetch_server_error(self, private_key_pem: str) -> None:
        instance = WeatherKitInstance(_config(private_key_pem))
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(500, json={}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_fetch_params(), client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NETWORK

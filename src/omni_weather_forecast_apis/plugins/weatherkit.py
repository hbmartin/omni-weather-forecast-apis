"""Apple WeatherKit REST API provider adapter."""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final
from zoneinfo import ZoneInfo

import httpx2
import jwt
from pydantic import Field, model_validator

from omni_weather_forecast_apis.mapping import (
    WEATHERKIT_CONDITION_MAP,
    km_from_meters,
    ms_from_kmh,
    safe_convert,
)
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_alert,
    build_daily_point,
    build_hourly_point,
    build_minutely_point,
    build_source_forecast,
    fallback_condition,
    first_present,
    normalize_percent,
    optional_max,
    optional_mean,
    probability_from_fraction,
)
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ErrorCode,
    Granularity,
    MinutelyDataPoint,
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    WeatherAlert,
    WeatherCondition,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.types.plugin import ProviderConfigModel


class WeatherKitConfig(ProviderConfigModel):
    team_id: str = Field(min_length=1)
    service_id: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    private_key: str | None = None
    private_key_path: str | None = None
    country_code: str | None = None
    hours: int = Field(default=48, ge=1, le=240)

    @model_validator(mode="after")
    def _exactly_one_key_source(self) -> WeatherKitConfig:
        if (self.private_key is None) == (self.private_key_path is None):
            msg = "provide exactly one of private_key or private_key_path"
            raise ValueError(msg)
        return self


WEATHERKIT_BASE_URL: Final = "https://weatherkit.apple.com/api/v1/weather"
_TOKEN_LIFETIME_SECONDS: Final = 3600
_TOKEN_REFRESH_MARGIN_SECONDS: Final = 600

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")

_MOON_PHASE_MAP: Final[dict[str, float]] = {
    "new": 0.0,
    "waxingCrescent": 0.125,
    "firstQuarter": 0.25,
    "waxingGibbous": 0.375,
    "full": 0.5,
    "waningGibbous": 0.625,
    "thirdQuarter": 0.75,
    "waningCrescent": 0.875,
}


def _section_items(
    payload: dict[str, Any],
    section_key: str,
    items_key: str,
) -> list[dict[str, Any]]:
    section = payload.get(section_key)
    if not isinstance(section, dict):
        return []
    items = section.get(items_key)
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _condition_code(entry: dict[str, Any]) -> str | None:
    code = entry.get("conditionCode")
    return code if isinstance(code, str) else None


def _condition(entry: dict[str, Any]) -> WeatherCondition | None:
    code = _condition_code(entry)
    if code is None:
        return None
    mapped = WEATHERKIT_CONDITION_MAP.get(code)
    return fallback_condition(mapped, _CAMEL_BOUNDARY.sub(" ", code))


def _parse_hour(entry: dict[str, Any]) -> WeatherDataPoint:
    daylight = entry.get("daylight")
    return build_hourly_point(
        entry["forecastStart"],
        temperature=as_float(entry.get("temperature")),
        apparent_temperature=as_float(entry.get("temperatureApparent")),
        dew_point=as_float(entry.get("temperatureDewPoint")),
        humidity=normalize_percent(entry.get("humidity")),
        wind_speed=safe_convert(as_float(entry.get("windSpeed")), ms_from_kmh),
        wind_gust=safe_convert(as_float(entry.get("windGust")), ms_from_kmh),
        wind_direction=as_float(entry.get("windDirection")),
        pressure_sea=as_float(entry.get("pressure")),
        precipitation=as_float(entry.get("precipitationAmount")),
        precipitation_probability=probability_from_fraction(
            entry.get("precipitationChance"),
        ),
        cloud_cover=normalize_percent(entry.get("cloudCover")),
        visibility=safe_convert(as_float(entry.get("visibility")), km_from_meters),
        uv_index=as_float(entry.get("uvIndex")),
        condition=_condition(entry),
        condition_code_original=_condition_code(entry),
        is_day=daylight if isinstance(daylight, bool) else None,
    )


def _day_part(entry: dict[str, Any], key: str) -> dict[str, Any]:
    part = entry.get(key)
    return part if isinstance(part, dict) else {}


def _parse_day(
    entry: dict[str, Any],
    location_timezone: ZoneInfo,
) -> DailyDataPoint:
    start = str(entry["forecastStart"])
    local_date = datetime.fromisoformat(start).astimezone(location_timezone).date()
    day_part = _day_part(entry, "daytimeForecast")
    night_part = _day_part(entry, "overnightForecast")
    moon_phase = entry.get("moonPhase")
    return build_daily_point(
        local_date,
        temperature_max=as_float(entry.get("temperatureMax")),
        temperature_min=as_float(entry.get("temperatureMin")),
        wind_speed_max=optional_max(
            safe_convert(as_float(day_part.get("windSpeed")), ms_from_kmh),
            safe_convert(as_float(night_part.get("windSpeed")), ms_from_kmh),
        ),
        wind_direction_dominant=as_float(day_part.get("windDirection")),
        precipitation_sum=as_float(entry.get("precipitationAmount")),
        precipitation_probability_max=probability_from_fraction(
            entry.get("precipitationChance"),
        ),
        snowfall_depth_sum=as_float(entry.get("snowfallAmount")),
        cloud_cover_mean=optional_mean(
            normalize_percent(day_part.get("cloudCover")),
            normalize_percent(night_part.get("cloudCover")),
        ),
        uv_index_max=as_float(entry.get("maxUvIndex")),
        humidity_mean=optional_mean(
            normalize_percent(day_part.get("humidity")),
            normalize_percent(night_part.get("humidity")),
        ),
        condition=_condition(entry) or _condition(day_part),
        sunrise=entry.get("sunrise"),
        sunset=entry.get("sunset"),
        moonrise=entry.get("moonrise"),
        moonset=entry.get("moonset"),
        moon_phase=(
            _MOON_PHASE_MAP.get(moon_phase) if isinstance(moon_phase, str) else None
        ),
    )


def _parse_minutes(payload: dict[str, Any]) -> list[MinutelyDataPoint]:
    return [
        build_minutely_point(
            entry["startTime"],
            precipitation_intensity=as_float(entry.get("precipitationIntensity")),
            precipitation_probability=probability_from_fraction(
                entry.get("precipitationChance"),
            ),
        )
        for entry in _section_items(payload, "forecastNextHour", "minutes")
    ]


def _parse_alerts(payload: dict[str, Any]) -> list[WeatherAlert]:
    alerts: list[WeatherAlert] = []
    for item in _section_items(payload, "weatherAlerts", "alerts"):
        start = first_present(item, "eventOnsetTime", "effectiveTime", "issuedTime")
        if not isinstance(start, str):
            continue
        description = item.get("description")
        event = description if isinstance(description, str) else "Weather alert"
        source = item.get("source")
        severity = item.get("severity")
        url = item.get("detailsUrl")
        alerts.append(
            build_alert(
                sender_name=source if isinstance(source, str) else "Apple WeatherKit",
                event=event,
                start=start,
                end=first_present(item, "eventEndTime", "expireTime"),
                description=event,
                severity=severity if isinstance(severity, str) else None,
                url=url if isinstance(url, str) else None,
            ),
        )
    return alerts


class WeatherKitInstance(BasePluginInstance[WeatherKitConfig]):
    """Configured Apple WeatherKit provider."""

    def __init__(self, config: WeatherKitConfig) -> None:
        super().__init__(
            ProviderId.WEATHERKIT,
            config,
            PluginCapabilities(
                granularity_minutely=True,
                granularity_hourly=True,
                granularity_daily=True,
                max_horizon_minutely_hours=1,
                max_horizon_hourly_hours=float(config.hours),
                max_horizon_daily_days=10,
                requires_api_key=True,
                multi_model=False,
                coverage="global",
                alerts=True,
            ),
        )
        self._cached_token: str | None = None
        self._token_expires_at: float = 0.0

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        token = self._bearer_token()
        if isinstance(token, PluginFetchError):
            return token

        data_sets = self._data_sets(params)
        if not data_sets:
            return self._success([])

        location_timezone = await self._resolve_location_timezone(params, client)
        if isinstance(location_timezone, PluginFetchError):
            return location_timezone

        payload = await self._get_json_dict(
            client,
            f"{WEATHERKIT_BASE_URL}/{params.language}"
            f"/{params.latitude}/{params.longitude}",
            params=self._query(data_sets, location_timezone),
            headers={"Authorization": f"Bearer {token}"},
            payload_name="WeatherKit",
        )
        if isinstance(payload, PluginFetchError):
            return payload

        try:
            hourly = [
                _parse_hour(entry)
                for entry in _section_items(payload, "forecastHourly", "hours")
            ]
            daily = [
                _parse_day(entry, location_timezone)
                for entry in _section_items(payload, "forecastDaily", "days")
            ]
            minutely = _parse_minutes(payload)
            alerts = _parse_alerts(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse WeatherKit payload: {exc}",
            )

        forecasts = [
            build_source_forecast(
                ProviderId.WEATHERKIT,
                timezone=location_timezone.key,
                minutely=minutely,
                hourly=hourly,
                daily=daily,
                alerts=alerts,
            ),
        ]
        return self._success(forecasts, raw=payload if params.include_raw else None)

    def _data_sets(self, params: PluginFetchParams) -> list[str]:
        requested = set(params.granularity)
        data_sets: list[str] = []
        if Granularity.MINUTELY in requested:
            data_sets.append("forecastNextHour")
        if Granularity.HOURLY in requested:
            data_sets.append("forecastHourly")
        if Granularity.DAILY in requested:
            data_sets.append("forecastDaily")
        if data_sets and self.config.country_code:
            data_sets.append("weatherAlerts")
        return data_sets

    def _query(
        self,
        data_sets: list[str],
        location_timezone: ZoneInfo,
    ) -> dict[str, str]:
        query = {
            "dataSets": ",".join(data_sets),
            "timezone": location_timezone.key,
        }
        if self.config.country_code:
            query["countryCode"] = self.config.country_code
        if "forecastHourly" in data_sets:
            hourly_end = datetime.now(UTC).replace(microsecond=0) + timedelta(
                hours=self.config.hours,
            )
            query["hourlyEnd"] = hourly_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        return query

    def _bearer_token(self, now: float | None = None) -> str | PluginFetchError:
        current = time.time() if now is None else now
        if (
            self._cached_token is not None
            and current < self._token_expires_at - _TOKEN_REFRESH_MARGIN_SECONDS
        ):
            return self._cached_token

        key_pem = self._private_key_pem()
        if isinstance(key_pem, PluginFetchError):
            return key_pem

        issued_at = int(current)
        try:
            token = jwt.encode(
                {
                    "iss": self.config.team_id,
                    "sub": self.config.service_id,
                    "iat": issued_at,
                    "exp": issued_at + _TOKEN_LIFETIME_SECONDS,
                },
                key_pem,
                algorithm="ES256",
                headers={
                    "kid": self.config.key_id,
                    "id": f"{self.config.team_id}.{self.config.service_id}",
                },
            )
        except (ValueError, TypeError, jwt.exceptions.PyJWTError) as exc:
            return self._error(
                ErrorCode.AUTH_FAILED,
                f"Could not sign WeatherKit token: {exc}",
            )
        self._cached_token = token
        self._token_expires_at = current + _TOKEN_LIFETIME_SECONDS
        return token

    def _private_key_pem(self) -> str | PluginFetchError:
        if self.config.private_key is not None:
            return self.config.private_key
        try:
            return Path(self.config.private_key_path or "").read_text(encoding="utf-8")
        except OSError as exc:
            return self._error(
                ErrorCode.AUTH_FAILED,
                f"Could not read WeatherKit private key: {exc}",
            )


class WeatherKitPlugin(BasePlugin[WeatherKitConfig]):
    """Apple WeatherKit plugin facade."""

    config_model = WeatherKitConfig
    instance_cls = WeatherKitInstance
    _id = ProviderId.WEATHERKIT
    _name = "Apple WeatherKit"


weatherkit_plugin = WeatherKitPlugin()

__all__ = ["WeatherKitConfig", "WeatherKitInstance", "weatherkit_plugin"]

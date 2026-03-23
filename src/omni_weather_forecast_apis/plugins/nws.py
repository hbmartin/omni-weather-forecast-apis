"""National Weather Service adapter."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import Field

from omni_weather_forecast_apis.mapping import condition_from_text
from omni_weather_forecast_apis.mapping.units import (
    celsius_from_fahrenheit,
    ms_from_mph,
)
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_alert,
    build_daily_point,
    build_hourly_point,
    build_source_forecast,
    normalize_probability,
)
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ErrorCode,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.types.plugin import ProviderConfigModel
from omni_weather_forecast_apis.utils import parse_datetime


class NWSGridOverride(ProviderConfigModel):
    office: str
    grid_x: int
    grid_y: int


class NWSConfig(ProviderConfigModel):
    user_agent: str = Field(min_length=1)
    grid_override: NWSGridOverride | None = None

if TYPE_CHECKING:
    import httpx

_BASE_URL = "https://api.weather.gov"
_CAPABILITIES = PluginCapabilities(
    granularity_minutely=False,
    granularity_hourly=True,
    granularity_daily=True,
    coverage="us_only",
    alerts=True,
    requires_api_key=False,
)
_CARDINAL_TO_DEGREES = {
    "N": 0.0,
    "NNE": 22.5,
    "NE": 45.0,
    "ENE": 67.5,
    "E": 90.0,
    "ESE": 112.5,
    "SE": 135.0,
    "SSE": 157.5,
    "S": 180.0,
    "SSW": 202.5,
    "SW": 225.0,
    "WSW": 247.5,
    "W": 270.0,
    "WNW": 292.5,
    "NW": 315.0,
    "NNW": 337.5,
}


def _nws_headers(user_agent: str) -> dict[str, str]:
    return {"User-Agent": user_agent, "Accept": "application/geo+json"}


def _wind_speed(speed_text: object) -> float | None:
    if not isinstance(speed_text, str):
        return None
    pieces = speed_text.replace("mph", "").replace("to", " ").split()
    numbers = [as_float(piece) for piece in pieces]
    values = [value for value in numbers if value is not None]
    if not values:
        return None
    return ms_from_mph(max(values))


def _wind_direction(direction: object) -> float | None:
    if not isinstance(direction, str):
        return None
    return _CARDINAL_TO_DEGREES.get(direction.strip().upper())


def _temperature(entry: Mapping[str, Any]) -> float | None:
    value = as_float(entry.get("temperature"))
    if value is None:
        return None
    unit = entry.get("temperatureUnit")
    return celsius_from_fahrenheit(value) if unit == "F" else value


def _probability(entry: Mapping[str, Any]) -> float | None:
    probability = entry.get("probabilityOfPrecipitation")
    if not isinstance(probability, Mapping):
        return None
    return normalize_probability(probability.get("value"))


def _local_start_date(period: Mapping[str, Any]) -> str | None:
    start_time = period.get("startTime")
    if not isinstance(start_time, str):
        if isinstance(start_time, bool):
            return None
        if not isinstance(start_time, (int, float, datetime)):
            return None
        if (start := parse_datetime(start_time)) is None:
            return None
        return start.date().isoformat()

    normalized = start_time.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        if (start := parse_datetime(start_time)) is None:
            return None
        return start.date().isoformat()


def _alert_url(
    feature: Mapping[str, Any],
    properties: Mapping[str, Any],
) -> str | None:
    for candidate in (feature.get("id"), feature.get("@id"), properties.get("@id")):
        if isinstance(candidate, str) and (normalized := candidate.strip()):
            return normalized
    return None


def _parse_hour(period: Mapping[str, Any]) -> WeatherDataPoint:
    short_forecast = period.get("shortForecast")
    return build_hourly_point(
        period["startTime"],
        temperature=_temperature(period),
        precipitation_probability=_probability(period),
        wind_speed=_wind_speed(period.get("windSpeed")),
        wind_direction=_wind_direction(period.get("windDirection")),
        condition=condition_from_text(
            short_forecast if isinstance(short_forecast, str) else None,
        ),
        condition_original=short_forecast if isinstance(short_forecast, str) else None,
        is_day=(
            bool(period.get("isDaytime"))
            if period.get("isDaytime") is not None
            else None
        ),
    )


def _combine_daily_periods(periods: list[Mapping[str, Any]]) -> list[DailyDataPoint]:
    combined: dict[str, dict[str, Any]] = {}
    for period in periods:
        if (key := _local_start_date(period)) is None:
            continue
        bucket = combined.setdefault(key, {"date": key})
        if period.get("isDaytime") is True:
            bucket["temperature_max"] = _temperature(period)
            bucket["summary"] = period.get("detailedForecast") or period.get(
                "shortForecast",
            )
            bucket["condition"] = condition_from_text(period.get("shortForecast"))
            bucket["wind_speed_max"] = _wind_speed(period.get("windSpeed"))
            bucket["wind_direction"] = _wind_direction(period.get("windDirection"))
        else:
            bucket["temperature_min"] = _temperature(period)
    return [
        build_daily_point(
            bucket["date"],
            temperature_max=bucket.get("temperature_max"),
            temperature_min=bucket.get("temperature_min"),
            wind_speed_max=bucket.get("wind_speed_max"),
            wind_direction_dominant=bucket.get("wind_direction"),
            condition=bucket.get("condition"),
            summary=bucket.get("summary"),
        )
        for bucket in combined.values()
    ]


class _NWSInstance(BasePluginInstance[NWSConfig]):
    """Configured NWS adapter."""

    def __init__(self, config: NWSConfig) -> None:
        super().__init__(ProviderId.NWS, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        """Fetch and normalize NWS forecast data."""

        headers = _nws_headers(self.config.user_agent)
        if self.config.grid_override is None:
            points_url = f"{_BASE_URL}/points/{params.latitude},{params.longitude}"
            points_raw, error = await self._get_json(
                client,
                points_url,
                headers=headers,
            )
            if error is not None:
                return error
            if not isinstance(points_raw, dict):
                return self._error(
                    ErrorCode.PARSE,
                    "Unexpected NWS points payload",
                    raw=points_raw,
                )
            properties = points_raw.get("properties")
            if not isinstance(properties, Mapping):
                return self._error(
                    ErrorCode.PARSE,
                    "NWS points payload missing properties",
                    raw=points_raw,
                )
            forecast_url = properties.get("forecast")
            hourly_url = properties.get("forecastHourly")
        else:
            override = self.config.grid_override
            forecast_url = (
                f"{_BASE_URL}/gridpoints/"
                f"{override.office}/{override.grid_x},{override.grid_y}/forecast"
            )
            hourly_url = f"{forecast_url}/hourly"

        if not isinstance(forecast_url, str) or not isinstance(hourly_url, str):
            return self._error(
                ErrorCode.NOT_AVAILABLE,
                "NWS forecast URLs could not be resolved",
            )

        raw_payload: dict[str, Any] = {}
        hourly: list[Any] = []
        daily: list[Any] = []

        hourly_raw, error = await self._get_json(client, hourly_url, headers=headers)
        if error is not None:
            return error
        if not isinstance(hourly_raw, dict):
            return self._error(
                ErrorCode.PARSE,
                "Unexpected NWS hourly payload",
                raw=hourly_raw,
            )
        raw_payload["hourly"] = hourly_raw
        hourly_properties = hourly_raw.get("properties")
        if isinstance(hourly_properties, Mapping):
            hourly = [
                _parse_hour(period)
                for period in hourly_properties.get("periods", [])
                if isinstance(period, Mapping) and "startTime" in period
            ]

        daily_raw, error = await self._get_json(client, forecast_url, headers=headers)
        if error is not None:
            return error
        if not isinstance(daily_raw, dict):
            return self._error(
                ErrorCode.PARSE,
                "Unexpected NWS daily payload",
                raw=daily_raw,
            )
        raw_payload["daily"] = daily_raw
        daily_properties = daily_raw.get("properties")
        if isinstance(daily_properties, Mapping):
            daily_periods = [
                period
                for period in daily_properties.get("periods", [])
                if isinstance(period, Mapping)
            ]
            daily = _combine_daily_periods(daily_periods)

        alerts_raw, error = await self._get_json(
            client,
            f"{_BASE_URL}/alerts/active",
            headers=headers,
            params={"point": f"{params.latitude},{params.longitude}"},
        )
        alerts: list[Any] = []
        if error is None and isinstance(alerts_raw, dict):
            raw_payload["alerts"] = alerts_raw
            alerts = [
                build_alert(
                    sender_name=str(properties.get("senderName") or "NWS"),
                    event=str(properties.get("event") or "Alert"),
                    start=(
                        properties["onset"]
                        if properties.get("onset") is not None
                        else properties["sent"]
                    ),
                    end=properties.get("ends"),
                    description=str(properties.get("description") or ""),
                    severity=properties.get("severity"),
                    url=_alert_url(feature, properties),
                )
                for feature in alerts_raw.get("features", [])
                if isinstance(feature, Mapping)
                if isinstance((properties := feature.get("properties")), Mapping)
                if properties.get("sent") is not None
                or properties.get("onset") is not None
            ]

        return self._success(
            [
                build_source_forecast(
                    self.provider_id,
                    hourly=hourly,
                    daily=daily,
                    alerts=alerts,
                ),
            ],
            raw=raw_payload if params.include_raw else None,
        )


class _NWSPlugin(BasePlugin[NWSConfig]):
    """NWS plugin facade."""

    config_model = NWSConfig
    instance_cls = _NWSInstance
    _id = ProviderId.NWS
    _name = "National Weather Service"


nws_plugin = _NWSPlugin()

__all__ = ["nws_plugin"]

"""Pirate Weather provider adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import httpx

from omni_weather_forecast_apis.mapping import WMO_CODE_MAP, condition_from_text
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_alert,
    build_daily_point,
    build_hourly_point,
    build_minutely_point,
    build_source_forecast,
    normalize_probability,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    PirateWeatherConfig,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
)
from omni_weather_forecast_apis.utils import parse_datetime

PIRATE_WEATHER_BASE_URL: Final = "https://api.pirateweather.net/forecast"


def _scaled_percent(value: Any) -> float | None:
    numeric = as_float(value)
    if numeric is None:
        return None
    return numeric * 100 if 0 <= numeric <= 1 else numeric


def _condition_for_entry(
    entry: dict[str, Any],
) -> tuple[Any, str | None, str | int | None]:
    if (numeric_code := as_float(entry.get("weatherCode"))) is not None:
        code = int(numeric_code)
        return WMO_CODE_MAP.get(code), entry.get("summary"), code
    icon = entry.get("icon")
    code_original = icon if isinstance(icon, str) else None
    summary = entry.get("summary") if isinstance(entry.get("summary"), str) else None
    return condition_from_text(summary), summary, code_original


def _daylight_duration(entry: dict[str, Any]) -> float | None:
    sunrise = parse_datetime(entry.get("sunriseTime"))
    sunset = parse_datetime(entry.get("sunsetTime"))
    if sunrise is None or sunset is None:
        return None
    return (sunset - sunrise).total_seconds()


def _sender_name(alert: dict[str, Any]) -> str:
    regions = alert.get("regions")
    if isinstance(regions, list) and regions:
        return str(regions[0])
    if isinstance(regions, str):
        return regions
    return str(alert.get("title", "pirate_weather"))


class PirateWeatherInstance(BasePluginInstance[PirateWeatherConfig]):
    """Configured Pirate Weather provider."""

    def __init__(self, config: PirateWeatherConfig) -> None:
        super().__init__(
            provider_id=ProviderId.PIRATE_WEATHER,
            config=config,
            capabilities=PluginCapabilities(
                granularity_minutely=True,
                granularity_hourly=True,
                granularity_daily=True,
                max_horizon_minutely_hours=1,
                max_horizon_hourly_hours=168 if config.extend_hourly else 48,
                max_horizon_daily_days=8,
                requires_api_key=True,
                multi_model=False,
                coverage="global",
                alerts=True,
            ),
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        payload, error = await self._get_json(
            client,
            (
                f"{PIRATE_WEATHER_BASE_URL}/{self.config.api_key}/"
                f"{params.latitude},{params.longitude}"
            ),
            params=self._request_params(params),
        )
        if error is not None:
            return error
        if payload is None or not isinstance(payload, dict):
            return self._error(
                ErrorCode.PARSE,
                "Pirate Weather returned an invalid payload",
            )

        try:
            forecasts = [
                build_source_forecast(
                    ProviderId.PIRATE_WEATHER,
                    minutely=self._parse_minutely(payload.get("minutely")),
                    hourly=self._parse_hourly(payload.get("hourly")),
                    daily=self._parse_daily(payload.get("daily")),
                    alerts=self._parse_alerts(payload.get("alerts")),
                ),
            ]
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse Pirate Weather payload: {exc}",
            )
        return self._success(forecasts, raw=payload if params.include_raw else None)

    def _request_params(self, params: PluginFetchParams) -> dict[str, str]:
        request_params = {
            "units": "si",
            "lang": params.language,
            "version": self.config.version,
        }
        if self.config.extend_hourly:
            request_params["extend"] = "hourly"
        return request_params

    def _parse_minutely(self, section: Any) -> list[Any]:
        data = section.get("data") if isinstance(section, dict) else None
        if not isinstance(data, list):
            return []

        points: list[Any] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            points.append(
                build_minutely_point(
                    row["time"],
                    precipitation_intensity=as_float(row.get("precipIntensity")),
                    precipitation_probability=normalize_probability(
                        row.get("precipProbability"),
                    ),
                ),
            )
        return points

    def _parse_hourly(self, section: Any) -> list[Any]:
        data = section.get("data") if isinstance(section, dict) else None
        if not isinstance(data, list):
            return []

        points: list[Any] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            condition, condition_original, condition_code = _condition_for_entry(row)
            points.append(
                build_hourly_point(
                    row["time"],
                    temperature=as_float(row.get("temperature")),
                    apparent_temperature=as_float(row.get("apparentTemperature")),
                    dew_point=as_float(row.get("dewPoint")),
                    humidity=_scaled_percent(row.get("humidity")),
                    wind_speed=as_float(row.get("windSpeed")),
                    wind_gust=as_float(row.get("windGust")),
                    wind_direction=as_float(row.get("windBearing")),
                    pressure_sea=as_float(row.get("pressure")),
                    precipitation=as_float(row.get("precipAccumulation"))
                    or as_float(row.get("precipIntensity")),
                    precipitation_probability=normalize_probability(
                        row.get("precipProbability"),
                    ),
                    rain=as_float(row.get("precipIntensity")),
                    snow=as_float(row.get("snowAccumulation")),
                    cloud_cover=_scaled_percent(row.get("cloudCover")),
                    visibility=as_float(row.get("visibility")),
                    uv_index=as_float(row.get("uvIndex")),
                    condition=condition,
                    condition_original=condition_original,
                    condition_code_original=condition_code,
                    is_day=(
                        bool(row["isDaytime"])
                        if isinstance(row.get("isDaytime"), bool)
                        else None
                    ),
                ),
            )
        return points

    def _parse_daily(self, section: Any) -> list[Any]:
        data = section.get("data") if isinstance(section, dict) else None
        if not isinstance(data, list):
            return []

        points: list[Any] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            condition, condition_original, _ = _condition_for_entry(row)
            points.append(
                build_daily_point(
                    row["time"],
                    temperature_max=as_float(row.get("temperatureHigh")),
                    temperature_min=as_float(row.get("temperatureLow")),
                    apparent_temperature_max=as_float(
                        row.get("apparentTemperatureHigh"),
                    ),
                    apparent_temperature_min=as_float(
                        row.get("apparentTemperatureLow"),
                    ),
                    wind_speed_max=as_float(row.get("windSpeed")),
                    wind_gust_max=as_float(row.get("windGust")),
                    wind_direction_dominant=as_float(row.get("windBearing")),
                    precipitation_sum=as_float(row.get("precipAccumulation")),
                    precipitation_probability_max=normalize_probability(
                        row.get("precipProbability"),
                    ),
                    rain_sum=as_float(row.get("precipAccumulation")),
                    snowfall_sum=as_float(row.get("snowAccumulation")),
                    cloud_cover_mean=_scaled_percent(row.get("cloudCover")),
                    uv_index_max=as_float(row.get("uvIndex")),
                    visibility_min=as_float(row.get("visibility")),
                    humidity_mean=_scaled_percent(row.get("humidity")),
                    pressure_sea_mean=as_float(row.get("pressure")),
                    condition=condition,
                    summary=condition_original,
                    sunrise=row.get("sunriseTime"),
                    sunset=row.get("sunsetTime"),
                    moonrise=row.get("moonriseTime"),
                    moonset=row.get("moonsetTime"),
                    moon_phase=as_float(row.get("moonPhase")),
                    daylight_duration=_daylight_duration(row),
                ),
            )
        return points

    def _parse_alerts(self, alerts: Any) -> list[Any]:
        if not isinstance(alerts, list):
            return []

        parsed_alerts: list[Any] = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            start = (
                alert.get("time")
                or alert.get("starts")
                or alert.get("expires")
                or int(datetime.now(tz=UTC).timestamp())
            )
            parsed_alerts.append(
                build_alert(
                    sender_name=_sender_name(alert),
                    event=str(alert.get("title", "Alert")),
                    start=start,
                    end=alert.get("expires"),
                    description=str(alert.get("description", "")),
                    severity=alert.get("severity"),
                    url=alert.get("uri"),
                ),
            )
        return parsed_alerts


class PirateWeatherPlugin(BasePlugin[PirateWeatherConfig]):
    """Pirate Weather plugin facade."""

    config_model = PirateWeatherConfig
    instance_cls = PirateWeatherInstance
    _id = ProviderId.PIRATE_WEATHER
    _name = "Pirate Weather"


pirate_weather_plugin = PirateWeatherPlugin()

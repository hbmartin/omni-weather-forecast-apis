"""Visual Crossing timeline adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from omni_weather_forecast_apis.mapping import condition_from_text
from omni_weather_forecast_apis.mapping.units import ms_from_kmh
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
    VisualCrossingConfig,
    WeatherDataPoint,
)

if TYPE_CHECKING:
    import httpx

_TIMELINE_URL = (
    "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/"
    "timeline"
)
_CAPABILITIES = PluginCapabilities(
    granularity_hourly=True,
    granularity_daily=True,
    max_horizon_hourly_hours=360,
    max_horizon_daily_days=15,
    alerts=True,
)


def _first_alert_time(*values: object) -> str | int | float | None:
    for value in values:
        if isinstance(value, (str, int, float)):
            return value
    return None


def _is_daylight(
    entry: Mapping[str, Any],
    day: Mapping[str, Any],
) -> bool | None:
    timestamp = entry.get("datetimeEpoch")
    sunrise = day.get("sunriseEpoch")
    sunset = day.get("sunsetEpoch")
    if not isinstance(timestamp, int):
        return None
    if not isinstance(sunrise, int) or not isinstance(sunset, int):
        return None
    return sunrise <= timestamp < sunset


def _parse_hour(
    entry: Mapping[str, Any],
    day: Mapping[str, Any],
) -> WeatherDataPoint:
    conditions = entry.get("conditions")
    icon = entry.get("icon")
    return build_hourly_point(
        entry["datetimeEpoch"],
        temperature=as_float(entry.get("temp")),
        apparent_temperature=as_float(entry.get("feelslike")),
        dew_point=as_float(entry.get("dew")),
        humidity=as_float(entry.get("humidity")),
        wind_speed=(
            ms_from_kmh(as_float(entry.get("windspeed")) or 0.0)
            if as_float(entry.get("windspeed")) is not None
            else None
        ),
        wind_gust=(
            ms_from_kmh(as_float(entry.get("windgust")) or 0.0)
            if as_float(entry.get("windgust")) is not None
            else None
        ),
        wind_direction=as_float(entry.get("winddir")),
        pressure_sea=as_float(entry.get("pressure")),
        precipitation=as_float(entry.get("precip")),
        precipitation_probability=normalize_probability(entry.get("precipprob")),
        cloud_cover=as_float(entry.get("cloudcover")),
        visibility=as_float(entry.get("visibility")),
        uv_index=as_float(entry.get("uvindex")),
        solar_radiation_ghi=as_float(entry.get("solarradiation")),
        condition=condition_from_text(
            conditions if isinstance(conditions, str) else None,
        ),
        condition_original=conditions if isinstance(conditions, str) else None,
        condition_code_original=icon if isinstance(icon, str) else None,
        is_day=_is_daylight(entry, day),
    )


def _parse_day(entry: Mapping[str, Any]) -> DailyDataPoint:
    conditions = entry.get("conditions")
    return build_daily_point(
        entry["datetime"],
        temperature_max=as_float(entry.get("tempmax")),
        temperature_min=as_float(entry.get("tempmin")),
        apparent_temperature_max=as_float(entry.get("feelslikemax")),
        apparent_temperature_min=as_float(entry.get("feelslikemin")),
        wind_speed_max=(
            ms_from_kmh(as_float(entry.get("windspeed")) or 0.0)
            if as_float(entry.get("windspeed")) is not None
            else None
        ),
        wind_gust_max=(
            ms_from_kmh(as_float(entry.get("windgust")) or 0.0)
            if as_float(entry.get("windgust")) is not None
            else None
        ),
        wind_direction_dominant=as_float(entry.get("winddir")),
        precipitation_sum=as_float(entry.get("precip")),
        precipitation_probability_max=normalize_probability(entry.get("precipprob")),
        cloud_cover_mean=as_float(entry.get("cloudcover")),
        uv_index_max=as_float(entry.get("uvindex")),
        visibility_min=as_float(entry.get("visibility")),
        humidity_mean=as_float(entry.get("humidity")),
        pressure_sea_mean=as_float(entry.get("pressure")),
        condition=condition_from_text(
            conditions if isinstance(conditions, str) else None,
        ),
        summary=conditions if isinstance(conditions, str) else None,
        sunrise=entry.get("sunriseEpoch"),
        sunset=entry.get("sunsetEpoch"),
        moon_phase=as_float(entry.get("moonphase")),
        solar_radiation_sum=as_float(entry.get("solarenergy")),
    )


class _VisualCrossingInstance(BasePluginInstance[VisualCrossingConfig]):
    """Configured Visual Crossing adapter."""

    def __init__(self, config: VisualCrossingConfig) -> None:
        super().__init__(ProviderId.VISUAL_CROSSING, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        """Fetch and normalize Visual Crossing forecast data."""

        url = f"{_TIMELINE_URL}/{params.latitude},{params.longitude}"
        raw, error = await self._get_json(
            client,
            url,
            params={
                "unitGroup": "metric",
                "include": self.config.include,
                "key": self.config.api_key,
                "lang": params.language,
            },
        )
        if error is not None:
            return error
        if not isinstance(raw, dict):
            return self._error(
                ErrorCode.PARSE,
                "Unexpected Visual Crossing payload",
                raw=raw,
            )

        days = [entry for entry in raw.get("days", []) if isinstance(entry, Mapping)]
        hourly = [
            _parse_hour(hour, day)
            for day in days
            for hour in day.get("hours", [])
            if isinstance(hour, Mapping) and "datetimeEpoch" in hour
        ]
        daily = [_parse_day(day) for day in days if "datetime" in day]
        alerts = [
            build_alert(
                sender_name=str(entry.get("source") or "Visual Crossing"),
                event=str(entry.get("event") or "Alert"),
                start=start,
                end=_first_alert_time(entry.get("endsEpoch"), entry.get("ends")),
                description=str(entry.get("description") or ""),
                severity=entry.get("severity"),
                url=entry.get("link"),
            )
            for entry in raw.get("alerts", [])
            if isinstance(entry, Mapping)
            if (
                start := _first_alert_time(
                    entry.get("onsetEpoch"),
                    entry.get("onset"),
                )
            )
            is not None
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
            raw=raw if params.include_raw else None,
        )


class _VisualCrossingPlugin(BasePlugin[VisualCrossingConfig]):
    """Visual Crossing plugin facade."""

    config_model = VisualCrossingConfig
    instance_cls = _VisualCrossingInstance
    _id = ProviderId.VISUAL_CROSSING
    _name = "Visual Crossing"


visual_crossing_plugin = _VisualCrossingPlugin()

__all__ = ["visual_crossing_plugin"]

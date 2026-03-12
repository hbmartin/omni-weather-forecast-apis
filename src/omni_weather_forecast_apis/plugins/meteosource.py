"""Meteosource point forecast adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

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
    normalize_probability,
)
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ErrorCode,
    MeteosourceConfig,
    MinutelyDataPoint,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    WeatherCondition,
    WeatherDataPoint,
)

if TYPE_CHECKING:
    import httpx

_POINT_URL = "https://www.meteosource.com/api/v1/free/point"
_CAPABILITIES = PluginCapabilities(
    granularity_minutely=True,
    granularity_hourly=True,
    granularity_daily=True,
    max_horizon_minutely_hours=1,
    max_horizon_hourly_hours=168,
    max_horizon_daily_days=30,
    alerts=True,
)
_ICON_NUM_MAP: dict[int, WeatherCondition] = {
    1: WeatherCondition.CLEAR,
    2: WeatherCondition.PARTLY_CLOUDY,
    3: WeatherCondition.OVERCAST,
    4: WeatherCondition.FOG,
    5: WeatherCondition.DRIZZLE,
    6: WeatherCondition.RAIN,
    7: WeatherCondition.SNOW,
    8: WeatherCondition.THUNDERSTORM,
}


def _condition(
    entry: Mapping[str, Any],
) -> tuple[WeatherCondition | None, str | None, int | None]:
    summary = first_present(entry, "summary", "weather", "description")
    icon_num = as_float(first_present(entry, "icon_num", "icon"))
    code = int(icon_num) if icon_num is not None else None
    return (
        fallback_condition(
            _ICON_NUM_MAP.get(code) if code is not None else None,
            summary if isinstance(summary, str) else None,
        ),
        summary if isinstance(summary, str) else None,
        code,
    )


def _parse_hour(entry: Mapping[str, Any]) -> WeatherDataPoint:
    condition, summary, code = _condition(entry)
    return build_hourly_point(
        first_present(entry, "date", "datetime", "time"),
        temperature=as_float(first_present(entry, "temperature", "temp")),
        apparent_temperature=as_float(
            first_present(entry, "feels_like", "apparent_temperature"),
        ),
        dew_point=as_float(first_present(entry, "dew_point", "dewpoint")),
        humidity=as_float(first_present(entry, "humidity", "relative_humidity")),
        wind_speed=as_float(first_present(entry, "wind_speed", "wind_speed_10m")),
        wind_gust=as_float(first_present(entry, "gust", "wind_gust")),
        wind_direction=as_float(first_present(entry, "wind_dir", "wind_direction")),
        pressure_sea=as_float(first_present(entry, "pressure", "pressure_msl")),
        precipitation=as_float(first_present(entry, "precipitation", "precip")),
        precipitation_probability=normalize_probability(
            first_present(entry, "precipitation_probability", "pop"),
        ),
        rain=as_float(first_present(entry, "rain", "precipitation")),
        snow=as_float(first_present(entry, "snow", "snowfall")),
        cloud_cover=as_float(first_present(entry, "cloud_cover", "clouds")),
        visibility=as_float(first_present(entry, "visibility", "visibility_km")),
        uv_index=as_float(first_present(entry, "uv_index", "uv")),
        condition=condition,
        condition_original=summary,
        condition_code_original=code,
        is_day=(
            bool(first_present(entry, "is_day", "day"))
            if first_present(entry, "is_day", "day") is not None
            else None
        ),
    )


def _parse_day(entry: Mapping[str, Any]) -> DailyDataPoint:
    condition, summary, _unused_code = _condition(entry)
    return build_daily_point(
        first_present(entry, "day", "date"),
        temperature_max=as_float(first_present(entry, "temperature_max", "maxtemp")),
        temperature_min=as_float(first_present(entry, "temperature_min", "mintemp")),
        apparent_temperature_max=as_float(
            first_present(entry, "feels_like_max", "apparent_temperature_max"),
        ),
        apparent_temperature_min=as_float(
            first_present(entry, "feels_like_min", "apparent_temperature_min"),
        ),
        wind_speed_max=as_float(first_present(entry, "wind_speed", "wind_max")),
        wind_gust_max=as_float(first_present(entry, "gust", "wind_gust")),
        wind_direction_dominant=as_float(
            first_present(entry, "wind_dir", "wind_direction"),
        ),
        precipitation_sum=as_float(first_present(entry, "all_day", "precipitation")),
        precipitation_probability_max=normalize_probability(
            first_present(entry, "precipitation_probability", "pop"),
        ),
        rain_sum=as_float(first_present(entry, "rain", "precipitation")),
        snowfall_sum=as_float(first_present(entry, "snow", "snowfall")),
        cloud_cover_mean=as_float(first_present(entry, "cloud_cover", "clouds")),
        uv_index_max=as_float(first_present(entry, "uv_index", "uv")),
        visibility_min=as_float(first_present(entry, "visibility", "visibility_km")),
        humidity_mean=as_float(first_present(entry, "humidity", "relative_humidity")),
        pressure_sea_mean=as_float(first_present(entry, "pressure", "pressure_msl")),
        condition=condition,
        summary=summary,
        sunrise=entry.get("sunrise"),
        sunset=entry.get("sunset"),
        moonrise=entry.get("moonrise"),
        moonset=entry.get("moonset"),
        moon_phase=as_float(entry.get("moon_phase")),
    )


class _MeteosourceInstance(BasePluginInstance[MeteosourceConfig]):
    """Configured Meteosource adapter."""

    def __init__(self, config: MeteosourceConfig) -> None:
        super().__init__(ProviderId.METEOSOURCE, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        """Fetch and normalize Meteosource forecast data."""

        raw, error = await self._get_json(
            client,
            _POINT_URL,
            params={
                "lat": params.latitude,
                "lon": params.longitude,
                "sections": ",".join(self.config.sections),
                "timezone": "UTC",
                "language": params.language,
                "units": "metric",
                "key": self.config.api_key,
            },
        )
        if error is not None:
            return error
        if not isinstance(raw, dict):
            return self._error(
                ErrorCode.PARSE,
                "Unexpected Meteosource payload",
                raw=raw,
            )

        minutely: list[MinutelyDataPoint] = [
            build_minutely_point(
                first_present(entry, "date", "datetime", "time"),
                precipitation_intensity=as_float(
                    first_present(entry, "precipitation", "precip"),
                ),
                precipitation_probability=normalize_probability(
                    first_present(entry, "precipitation_probability", "pop"),
                ),
            )
            for entry in raw.get("minutely", [])
            if isinstance(entry, Mapping)
        ]
        hourly = [
            _parse_hour(entry)
            for entry in raw.get("hourly", [])
            if isinstance(entry, Mapping)
        ]
        daily = [
            _parse_day(entry)
            for entry in raw.get("daily", [])
            if isinstance(entry, Mapping)
        ]
        alerts = [
            build_alert(
                sender_name=str(entry.get("source") or "Meteosource"),
                event=str(entry.get("event") or "Alert"),
                start=entry["start"],
                end=entry.get("end"),
                description=str(entry.get("description") or ""),
                severity=entry.get("severity"),
                url=entry.get("url"),
            )
            for entry in raw.get("alerts", [])
            if isinstance(entry, Mapping) and "start" in entry
        ]
        return self._success(
            [
                build_source_forecast(
                    self.provider_id,
                    minutely=minutely,
                    hourly=hourly,
                    daily=daily,
                    alerts=alerts,
                ),
            ],
            raw=raw if params.include_raw else None,
        )


class _MeteosourcePlugin(BasePlugin[MeteosourceConfig]):
    """Meteosource plugin facade."""

    config_model = MeteosourceConfig
    instance_cls = _MeteosourceInstance
    _id = ProviderId.METEOSOURCE
    _name = "Meteosource"


meteosource_plugin = _MeteosourcePlugin()

__all__ = ["meteosource_plugin"]

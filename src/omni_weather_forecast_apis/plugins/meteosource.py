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


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_of(*values: Any) -> Any | None:
    for value in values:
        if value is not None:
            return value
    return None


def _nested_value(mapping: Mapping[str, Any], *path: str) -> Any | None:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _section_rows(raw: Mapping[str, Any], section_name: str) -> list[Mapping[str, Any]]:
    section = raw.get(section_name)
    if isinstance(section, list):
        return [entry for entry in section if isinstance(entry, Mapping)]
    if isinstance(section, Mapping) and isinstance(section.get("data"), list):
        return [entry for entry in section["data"] if isinstance(entry, Mapping)]
    return []


def _parse_is_day(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if (numeric := as_float(value)) is not None:
        return bool(int(numeric))
    return None


def _condition(
    entry: Mapping[str, Any],
) -> tuple[WeatherCondition | None, str | None, int | None]:
    weather = _as_mapping(entry.get("weather"))
    summary = _first_of(
        first_present(weather, "summary", "description"),
        first_present(entry, "summary", "weather", "description"),
    )
    icon_num = as_float(
        _first_of(
            first_present(weather, "icon_num", "icon"),
            first_present(entry, "icon_num", "icon"),
        ),
    )
    code = int(icon_num) if icon_num is not None else None
    return (
        fallback_condition(
            _ICON_NUM_MAP.get(code) if code is not None else None,
            summary if isinstance(summary, str) else None,
        ),
        summary if isinstance(summary, str) else None,
        code,
    )


def _parse_minutely(entry: Mapping[str, Any]) -> MinutelyDataPoint:
    precipitation = _as_mapping(entry.get("precipitation"))
    probability = _as_mapping(entry.get("probability"))
    return build_minutely_point(
        first_present(entry, "date", "datetime", "time"),
        precipitation_intensity=as_float(
            _first_of(
                first_present(precipitation, "total", "precip"),
                first_present(entry, "precipitation", "precip"),
            ),
        ),
        precipitation_probability=normalize_probability(
            _first_of(
                first_present(probability, "precipitation", "pop"),
                first_present(entry, "precipitation_probability", "pop"),
            ),
        ),
    )


def _parse_hour(entry: Mapping[str, Any]) -> WeatherDataPoint:
    wind = _as_mapping(entry.get("wind"))
    precipitation = _as_mapping(entry.get("precipitation"))
    probability = _as_mapping(entry.get("probability"))
    cloud_cover = _as_mapping(entry.get("cloud_cover"))
    condition, summary, code = _condition(entry)
    is_day_raw = first_present(entry, "is_day", "day")
    return build_hourly_point(
        first_present(entry, "date", "datetime", "time"),
        temperature=as_float(first_present(entry, "temperature", "temp")),
        apparent_temperature=as_float(
            first_present(entry, "feels_like", "apparent_temperature"),
        ),
        dew_point=as_float(first_present(entry, "dew_point", "dewpoint")),
        humidity=as_float(first_present(entry, "humidity", "relative_humidity")),
        wind_speed=as_float(
            _first_of(
                first_present(wind, "speed", "wind_speed", "wind_speed_10m"),
                first_present(entry, "wind_speed", "wind_speed_10m"),
            ),
        ),
        wind_gust=as_float(
            _first_of(
                first_present(wind, "gust", "gusts", "wind_gust"),
                first_present(entry, "gust", "wind_gust"),
            ),
        ),
        wind_direction=as_float(
            _first_of(
                first_present(wind, "angle", "direction", "wind_direction"),
                first_present(entry, "wind_dir", "wind_direction"),
            ),
        ),
        pressure_sea=as_float(first_present(entry, "pressure", "pressure_msl")),
        precipitation=as_float(
            _first_of(
                first_present(precipitation, "total", "precip"),
                first_present(entry, "precipitation", "precip"),
            ),
        ),
        precipitation_probability=normalize_probability(
            _first_of(
                first_present(probability, "precipitation", "pop"),
                first_present(entry, "precipitation_probability", "pop"),
            ),
        ),
        rain=as_float(
            _first_of(
                first_present(precipitation, "rain"),
                first_present(entry, "rain"),
            ),
        ),
        snow=as_float(
            _first_of(
                first_present(precipitation, "snow", "snowfall"),
                first_present(entry, "snow", "snowfall"),
            ),
        ),
        cloud_cover=as_float(
            _first_of(
                first_present(cloud_cover, "total", "cloud_cover"),
                first_present(entry, "cloud_cover", "clouds"),
            ),
        ),
        visibility=as_float(first_present(entry, "visibility", "visibility_km")),
        uv_index=as_float(first_present(entry, "uv_index", "uv")),
        condition=condition,
        condition_original=summary,
        condition_code_original=code,
        is_day=_parse_is_day(is_day_raw),
    )


def _parse_day(entry: Mapping[str, Any]) -> DailyDataPoint:
    all_day = _as_mapping(entry.get("all_day"))
    wind = _as_mapping(all_day.get("wind") or entry.get("wind"))
    precipitation = _as_mapping(
        all_day.get("precipitation") or entry.get("precipitation"),
    )
    probability = _as_mapping(
        all_day.get("probability") or entry.get("probability"),
    )
    cloud_cover = _as_mapping(
        all_day.get("cloud_cover") or entry.get("cloud_cover"),
    )
    sun = _as_mapping(_nested_value(entry, "astro", "sun"))
    moon = _as_mapping(_nested_value(entry, "astro", "moon"))
    condition, summary, _unused_code = _condition(all_day)
    if condition is None and summary is None:
        condition, summary, _unused_code = _condition(entry)
    return build_daily_point(
        first_present(entry, "day", "date"),
        temperature_max=as_float(
            _first_of(
                first_present(all_day, "temperature_max", "maxtemp"),
                first_present(entry, "temperature_max", "maxtemp"),
            ),
        ),
        temperature_min=as_float(
            _first_of(
                first_present(all_day, "temperature_min", "mintemp"),
                first_present(entry, "temperature_min", "mintemp"),
            ),
        ),
        apparent_temperature_max=as_float(
            _first_of(
                first_present(all_day, "feels_like_max", "apparent_temperature_max"),
                first_present(entry, "feels_like_max", "apparent_temperature_max"),
            ),
        ),
        apparent_temperature_min=as_float(
            _first_of(
                first_present(all_day, "feels_like_min", "apparent_temperature_min"),
                first_present(entry, "feels_like_min", "apparent_temperature_min"),
            ),
        ),
        wind_speed_max=as_float(
            _first_of(
                first_present(wind, "speed", "wind_speed", "wind_max"),
                first_present(entry, "wind_speed", "wind_max"),
            ),
        ),
        wind_gust_max=as_float(
            _first_of(
                first_present(wind, "gust", "gusts", "wind_gust"),
                first_present(entry, "gust", "wind_gust"),
            ),
        ),
        wind_direction_dominant=as_float(
            _first_of(
                first_present(wind, "angle", "direction", "wind_direction"),
                first_present(entry, "wind_dir", "wind_direction"),
            ),
        ),
        precipitation_sum=as_float(
            _first_of(
                first_present(precipitation, "total", "precip"),
                first_present(all_day, "precipitation"),
                first_present(entry, "precipitation"),
            ),
        ),
        precipitation_probability_max=normalize_probability(
            _first_of(
                first_present(probability, "precipitation", "pop"),
                first_present(all_day, "precipitation_probability", "pop"),
                first_present(entry, "precipitation_probability", "pop"),
            ),
        ),
        rain_sum=as_float(
            _first_of(
                first_present(precipitation, "rain"),
                first_present(all_day, "rain"),
                first_present(entry, "rain"),
            ),
        ),
        snowfall_sum=as_float(
            _first_of(
                first_present(precipitation, "snow", "snowfall"),
                first_present(all_day, "snow", "snowfall"),
                first_present(entry, "snow", "snowfall"),
            ),
        ),
        cloud_cover_mean=as_float(
            _first_of(
                first_present(cloud_cover, "total", "cloud_cover"),
                first_present(all_day, "cloud_cover", "clouds"),
                first_present(entry, "cloud_cover", "clouds"),
            ),
        ),
        uv_index_max=as_float(
            _first_of(
                first_present(all_day, "uv_index", "uv"),
                first_present(entry, "uv_index", "uv"),
            ),
        ),
        visibility_min=as_float(
            _first_of(
                first_present(all_day, "visibility", "visibility_km"),
                first_present(entry, "visibility", "visibility_km"),
            ),
        ),
        humidity_mean=as_float(
            _first_of(
                first_present(all_day, "humidity", "relative_humidity"),
                first_present(entry, "humidity", "relative_humidity"),
            ),
        ),
        pressure_sea_mean=as_float(
            _first_of(
                first_present(all_day, "pressure", "pressure_msl"),
                first_present(entry, "pressure", "pressure_msl"),
            ),
        ),
        condition=condition,
        summary=summary,
        sunrise=_first_of(sun.get("rise"), entry.get("sunrise")),
        sunset=_first_of(sun.get("set"), entry.get("sunset")),
        moonrise=_first_of(moon.get("rise"), entry.get("moonrise")),
        moonset=_first_of(moon.get("set"), entry.get("moonset")),
        moon_phase=as_float(_first_of(moon.get("phase"), entry.get("moon_phase"))),
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
        try:
            minutely: list[MinutelyDataPoint] = []
            for entry in _section_rows(raw, "minutely"):
                try:
                    minutely.append(_parse_minutely(entry))
                except KeyError, TypeError, ValueError:
                    continue

            hourly: list[WeatherDataPoint] = []
            for entry in _section_rows(raw, "hourly"):
                try:
                    hourly.append(_parse_hour(entry))
                except KeyError, TypeError, ValueError:
                    continue

            daily: list[DailyDataPoint] = []
            for entry in _section_rows(raw, "daily"):
                try:
                    daily.append(_parse_day(entry))
                except KeyError, TypeError, ValueError:
                    continue

            alerts = []
            for entry in _section_rows(raw, "alerts"):
                start = first_present(entry, "start", "starts")
                if start is None:
                    continue
                try:
                    alerts.append(
                        build_alert(
                            sender_name=str(entry.get("source") or "Meteosource"),
                            event=str(entry.get("event") or "Alert"),
                            start=start,
                            end=entry.get("end"),
                            description=str(entry.get("description") or ""),
                            severity=entry.get("severity"),
                            url=entry.get("url"),
                        ),
                    )
                except KeyError, TypeError, ValueError:
                    continue
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse Meteosource payload: {exc}",
                raw=raw,
            )
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

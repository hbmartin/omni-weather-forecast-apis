"""Open-Meteo provider adapter."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Final

import httpx

from omni_weather_forecast_apis.mapping import WMO_CODE_MAP, km_from_meters
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_daily_point,
    build_hourly_point,
    build_minutely_point,
    build_source_forecast,
    normalize_probability,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    OpenMeteoConfig,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
)

OPEN_METEO_URL: Final = "https://api.open-meteo.com/v1/forecast"
DEFAULT_HOURLY_FIELDS: Final[tuple[str, ...]] = (
    "temperature_2m",
    "apparent_temperature",
    "dew_point_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "pressure_msl",
    "surface_pressure",
    "precipitation",
    "precipitation_probability",
    "rain",
    "snowfall",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "visibility",
    "uv_index",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "weather_code",
    "is_day",
)
DEFAULT_DAILY_FIELDS: Final[tuple[str, ...]] = (
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
    "precipitation_sum",
    "precipitation_probability_max",
    "rain_sum",
    "snowfall_sum",
    "cloud_cover_mean",
    "uv_index_max",
    "visibility_min",
    "relative_humidity_2m_mean",
    "pressure_msl_mean",
    "weather_code",
    "sunrise",
    "sunset",
    "daylight_duration",
    "shortwave_radiation_sum",
)
DEFAULT_MINUTELY_FIELDS: Final[tuple[str, ...]] = (
    "precipitation",
    "precipitation_probability",
)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _parallel_rows(section: dict[str, Any]) -> list[dict[str, Any]]:
    times = section.get("time")
    if not isinstance(times, list):
        return []

    rows: list[dict[str, Any]] = []
    for index, time_value in enumerate(times):
        row: dict[str, Any] = {"time": time_value}
        for key, values in section.items():
            if key == "time" or not isinstance(values, list) or index >= len(values):
                continue
            row[key] = values[index]
        rows.append(row)
    return rows


def _condition_from_code(value: Any) -> tuple[Any, Any]:
    if (numeric := as_float(value)) is None:
        return None, None
    code = int(numeric)
    return WMO_CODE_MAP.get(code), code


def _parse_is_day(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if (numeric := as_float(value)) is None:
        return None
    return bool(int(numeric))


class OpenMeteoInstance(BasePluginInstance[OpenMeteoConfig]):
    """Configured Open-Meteo provider."""

    def __init__(self, config: OpenMeteoConfig) -> None:
        super().__init__(
            provider_id=ProviderId.OPEN_METEO,
            config=config,
            capabilities=PluginCapabilities(
                granularity_minutely=True,
                granularity_hourly=True,
                granularity_daily=True,
                max_horizon_minutely_hours=1,
                max_horizon_hourly_hours=16 * 24,
                max_horizon_daily_days=16,
                requires_api_key=False,
                multi_model=True,
                coverage="global",
            ),
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        payload, error = await self._get_json(
            client,
            OPEN_METEO_URL,
            params=self._request_params(params),
        )
        if error is not None:
            return error
        if payload is None:
            return self._error(ErrorCode.UNKNOWN, "Open-Meteo returned no payload")

        try:
            forecasts = self._parse_payloads(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse Open-Meteo payload: {exc}",
            )
        return self._success(forecasts, raw=payload if params.include_raw else None)

    def _request_params(self, params: PluginFetchParams) -> dict[str, str | float]:
        request_params: dict[str, str | float] = {
            "latitude": params.latitude,
            "longitude": params.longitude,
            "timezone": "UTC",
        }
        if self.config.api_key is not None:
            request_params["apikey"] = self.config.api_key
        if self.config.models:
            request_params["models"] = ",".join(self.config.models)
        if Granularity.HOURLY in params.granularity:
            request_params["hourly"] = ",".join(
                _dedupe(
                    (
                        *DEFAULT_HOURLY_FIELDS,
                        *(self.config.extra_hourly_vars or ()),
                    ),
                ),
            )
        if Granularity.DAILY in params.granularity:
            request_params["daily"] = ",".join(
                _dedupe(
                    (
                        *DEFAULT_DAILY_FIELDS,
                        *(self.config.extra_daily_vars or ()),
                    ),
                ),
            )
        if Granularity.MINUTELY in params.granularity:
            request_params["minutely_15"] = ",".join(DEFAULT_MINUTELY_FIELDS)
        return request_params

    def _get_section(
        self,
        data: dict[str, Any],
        section: str,
        model: str,
    ) -> dict[str, Any] | None:
        """Get a data section, handling multi-model key suffixes.

        Open-Meteo returns flat keys with model suffixes for multi-model
        requests (e.g. ``hourly_ecmwf``, ``daily_gfs``).  For the default
        ``best_match`` model the un-suffixed key is used.
        """
        if model != "best_match" and f"{section}_{model}" in data:
            return data[f"{section}_{model}"]
        return data.get(section)

    def _parse_payloads(self, payload: dict[str, Any] | list[Any]) -> list[Any]:
        data = payload if isinstance(payload, dict) else {}
        forecasts: list[Any] = []
        for model in self.config.models:
            forecasts.append(
                build_source_forecast(
                    ProviderId.OPEN_METEO,
                    model=model,
                    minutely=self._parse_minutely(
                        self._get_section(data, "minutely_15", model),
                    ),
                    hourly=self._parse_hourly(
                        self._get_section(data, "hourly", model),
                    ),
                    daily=self._parse_daily(
                        self._get_section(data, "daily", model),
                    ),
                ),
            )
        return forecasts

    def _parse_minutely(self, section: Any) -> list[Any]:
        if not isinstance(section, dict):
            return []

        points: list[Any] = []
        for row in _parallel_rows(section):
            points.append(
                build_minutely_point(
                    row["time"],
                    precipitation_intensity=as_float(row.get("precipitation")),
                    precipitation_probability=normalize_probability(
                        row.get("precipitation_probability"),
                    ),
                ),
            )
        return points

    def _parse_hourly(self, section: Any) -> list[Any]:
        if not isinstance(section, dict):
            return []

        points: list[Any] = []
        for row in _parallel_rows(section):
            condition, code = _condition_from_code(row.get("weather_code"))
            visibility = as_float(row.get("visibility"))
            points.append(
                build_hourly_point(
                    row["time"],
                    temperature=as_float(row.get("temperature_2m")),
                    apparent_temperature=as_float(row.get("apparent_temperature")),
                    dew_point=as_float(row.get("dew_point_2m")),
                    humidity=as_float(row.get("relative_humidity_2m")),
                    wind_speed=as_float(row.get("wind_speed_10m")),
                    wind_gust=as_float(row.get("wind_gusts_10m")),
                    wind_direction=as_float(row.get("wind_direction_10m")),
                    pressure_sea=as_float(row.get("pressure_msl")),
                    pressure_surface=as_float(row.get("surface_pressure")),
                    precipitation=as_float(row.get("precipitation")),
                    precipitation_probability=normalize_probability(
                        row.get("precipitation_probability"),
                    ),
                    rain=as_float(row.get("rain")),
                    snow=as_float(row.get("snowfall")),
                    cloud_cover=as_float(row.get("cloud_cover")),
                    cloud_cover_low=as_float(row.get("cloud_cover_low")),
                    cloud_cover_mid=as_float(row.get("cloud_cover_mid")),
                    cloud_cover_high=as_float(row.get("cloud_cover_high")),
                    visibility=(
                        km_from_meters(visibility) if visibility is not None else None
                    ),
                    uv_index=as_float(row.get("uv_index")),
                    solar_radiation_ghi=as_float(row.get("shortwave_radiation")),
                    solar_radiation_dni=as_float(row.get("direct_radiation")),
                    solar_radiation_dhi=as_float(row.get("diffuse_radiation")),
                    condition=condition,
                    condition_code_original=code,
                    is_day=_parse_is_day(row.get("is_day")),
                ),
            )
        return points

    def _parse_daily(self, section: Any) -> list[Any]:
        if not isinstance(section, dict):
            return []

        points: list[Any] = []
        for row in _parallel_rows(section):
            condition, _ = _condition_from_code(row.get("weather_code"))
            visibility = as_float(row.get("visibility_min"))
            points.append(
                build_daily_point(
                    row["time"],
                    temperature_max=as_float(row.get("temperature_2m_max")),
                    temperature_min=as_float(row.get("temperature_2m_min")),
                    apparent_temperature_max=as_float(
                        row.get("apparent_temperature_max"),
                    ),
                    apparent_temperature_min=as_float(
                        row.get("apparent_temperature_min"),
                    ),
                    wind_speed_max=as_float(row.get("wind_speed_10m_max")),
                    wind_gust_max=as_float(row.get("wind_gusts_10m_max")),
                    wind_direction_dominant=as_float(
                        row.get("wind_direction_10m_dominant"),
                    ),
                    precipitation_sum=as_float(row.get("precipitation_sum")),
                    precipitation_probability_max=normalize_probability(
                        row.get("precipitation_probability_max"),
                    ),
                    rain_sum=as_float(row.get("rain_sum")),
                    snowfall_sum=as_float(row.get("snowfall_sum")),
                    cloud_cover_mean=as_float(row.get("cloud_cover_mean")),
                    uv_index_max=as_float(row.get("uv_index_max")),
                    visibility_min=(
                        km_from_meters(visibility) if visibility is not None else None
                    ),
                    humidity_mean=as_float(row.get("relative_humidity_2m_mean")),
                    pressure_sea_mean=as_float(row.get("pressure_msl_mean")),
                    condition=condition,
                    summary=None,
                    sunrise=row.get("sunrise"),
                    sunset=row.get("sunset"),
                    daylight_duration=as_float(row.get("daylight_duration")),
                    solar_radiation_sum=as_float(row.get("shortwave_radiation_sum")),
                ),
            )
        return points


class OpenMeteoPlugin(BasePlugin[OpenMeteoConfig]):
    """Open-Meteo plugin facade."""

    config_model = OpenMeteoConfig
    instance_cls = OpenMeteoInstance
    _id = ProviderId.OPEN_METEO
    _name = "Open-Meteo"


open_meteo_plugin = OpenMeteoPlugin()

"""Weatherbit adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from omni_weather_forecast_apis.mapping import condition_from_text
from omni_weather_forecast_apis.mapping.units import (
    celsius_from_fahrenheit,
    mm_from_inches,
    ms_from_mph,
)
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_daily_point,
    build_hourly_point,
    build_source_forecast,
    normalize_probability,
)
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ErrorCode,
    Granularity,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    WeatherbitConfig,
    WeatherCondition,
    WeatherDataPoint,
)

if TYPE_CHECKING:
    import httpx

_HOURLY_URL = "https://api.weatherbit.io/v2.0/forecast/hourly"
_DAILY_URL = "https://api.weatherbit.io/v2.0/forecast/daily"
_CAPABILITIES = PluginCapabilities(
    granularity_hourly=True,
    granularity_daily=True,
    max_horizon_hourly_hours=240,
    max_horizon_daily_days=16,
)
_WEATHERBIT_CONDITION_MAP: dict[int, WeatherCondition] = {
    200: WeatherCondition.THUNDERSTORM_RAIN,
    201: WeatherCondition.THUNDERSTORM_RAIN,
    202: WeatherCondition.THUNDERSTORM_HEAVY,
    230: WeatherCondition.THUNDERSTORM_RAIN,
    231: WeatherCondition.THUNDERSTORM_RAIN,
    232: WeatherCondition.THUNDERSTORM_HEAVY,
    233: WeatherCondition.HAIL,
    300: WeatherCondition.DRIZZLE,
    301: WeatherCondition.DRIZZLE,
    302: WeatherCondition.DRIZZLE,
    500: WeatherCondition.LIGHT_RAIN,
    501: WeatherCondition.RAIN,
    502: WeatherCondition.HEAVY_RAIN,
    511: WeatherCondition.FREEZING_RAIN,
    520: WeatherCondition.LIGHT_RAIN,
    521: WeatherCondition.RAIN,
    522: WeatherCondition.HEAVY_RAIN,
    600: WeatherCondition.LIGHT_SNOW,
    601: WeatherCondition.SNOW,
    602: WeatherCondition.HEAVY_SNOW,
    610: WeatherCondition.SLEET,
    611: WeatherCondition.SLEET,
    612: WeatherCondition.SLEET,
    621: WeatherCondition.LIGHT_SNOW,
    622: WeatherCondition.HEAVY_SNOW,
    623: WeatherCondition.LIGHT_SNOW,
    700: WeatherCondition.HAZE,
    711: WeatherCondition.SMOKE,
    721: WeatherCondition.HAZE,
    731: WeatherCondition.DUST,
    741: WeatherCondition.FOG,
    751: WeatherCondition.FOG,
    800: WeatherCondition.CLEAR,
    801: WeatherCondition.MOSTLY_CLEAR,
    802: WeatherCondition.PARTLY_CLOUDY,
    803: WeatherCondition.MOSTLY_CLOUDY,
    804: WeatherCondition.OVERCAST,
    900: WeatherCondition.UNKNOWN,
}


def _normalize_temperature(value: float | None, units: str) -> float | None:
    if value is None:
        return None
    return celsius_from_fahrenheit(value) if units == "I" else value


def _normalize_precipitation(value: float | None, units: str) -> float | None:
    if value is None:
        return None
    return mm_from_inches(value) if units == "I" else value


def _normalize_wind(value: float | None, units: str) -> float | None:
    if value is None:
        return None
    return ms_from_mph(value) if units == "I" else value


def _parse_condition(weather: object) -> tuple[str | None, int | None]:
    if not isinstance(weather, dict):
        return None, None
    weather_data = cast("dict[str, object]", weather)
    description = weather_data.get("description")
    code = weather_data.get("code")
    return description if isinstance(description, str) else None, (
        code if isinstance(code, int) else None
    )


def _map_condition(
    description: str | None,
    code: int | None,
) -> WeatherCondition | None:
    if code is None:
        return condition_from_text(description)
    return _WEATHERBIT_CONDITION_MAP.get(code, condition_from_text(description))


def _parse_hour(entry: Mapping[str, Any], units: str) -> WeatherDataPoint:
    description, code = _parse_condition(entry.get("weather"))
    return build_hourly_point(
        entry["timestamp_utc"] if "timestamp_utc" in entry else entry["ts"],
        temperature=_normalize_temperature(as_float(entry.get("temp")), units),
        apparent_temperature=_normalize_temperature(
            as_float(entry.get("app_temp")),
            units,
        ),
        dew_point=_normalize_temperature(as_float(entry.get("dewpt")), units),
        humidity=as_float(entry.get("rh")),
        wind_speed=_normalize_wind(as_float(entry.get("wind_spd")), units),
        wind_gust=_normalize_wind(as_float(entry.get("wind_gust_spd")), units),
        wind_direction=as_float(entry.get("wind_dir")),
        pressure_sea=as_float(entry.get("slp")),
        pressure_surface=as_float(entry.get("pres")),
        precipitation=_normalize_precipitation(as_float(entry.get("precip")), units),
        precipitation_probability=normalize_probability(entry.get("pop")),
        rain=_normalize_precipitation(as_float(entry.get("precip")), units),
        snow=_normalize_precipitation(as_float(entry.get("snow")), units),
        snow_depth=as_float(entry.get("snow_depth")),
        cloud_cover=as_float(entry.get("clouds")),
        visibility=as_float(entry.get("vis")),
        uv_index=as_float(entry.get("uv")),
        condition=_map_condition(description, code),
        condition_original=description,
        condition_code_original=code,
    )


def _parse_day(entry: Mapping[str, Any], units: str) -> DailyDataPoint:
    description, code = _parse_condition(entry.get("weather"))
    return build_daily_point(
        entry["valid_date"],
        temperature_max=_normalize_temperature(as_float(entry.get("max_temp")), units),
        temperature_min=_normalize_temperature(as_float(entry.get("min_temp")), units),
        apparent_temperature_max=_normalize_temperature(
            as_float(entry.get("app_max_temp")),
            units,
        ),
        apparent_temperature_min=_normalize_temperature(
            as_float(entry.get("app_min_temp")),
            units,
        ),
        wind_speed_max=_normalize_wind(as_float(entry.get("max_wind_spd")), units),
        wind_gust_max=_normalize_wind(as_float(entry.get("max_wind_gust_spd")), units),
        wind_direction_dominant=as_float(entry.get("wind_dir")),
        precipitation_sum=_normalize_precipitation(
            as_float(entry.get("precip")),
            units,
        ),
        precipitation_probability_max=normalize_probability(entry.get("pop")),
        rain_sum=_normalize_precipitation(as_float(entry.get("precip")), units),
        snowfall_sum=_normalize_precipitation(as_float(entry.get("snow")), units),
        cloud_cover_mean=as_float(entry.get("clouds")),
        uv_index_max=as_float(entry.get("uv")),
        visibility_min=as_float(entry.get("vis")),
        humidity_mean=as_float(entry.get("rh")),
        pressure_sea_mean=as_float(entry.get("slp")),
        condition=_map_condition(description, code),
        summary=description,
        sunrise=entry.get("sunrise_ts"),
        sunset=entry.get("sunset_ts"),
        moonrise=entry.get("moonrise_ts"),
        moonset=entry.get("moonset_ts"),
        moon_phase=as_float(entry.get("moon_phase")),
    )


class _WeatherbitInstance(BasePluginInstance[WeatherbitConfig]):
    """Configured Weatherbit adapter."""

    def __init__(self, config: WeatherbitConfig) -> None:
        super().__init__(ProviderId.WEATHERBIT, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        """Fetch and normalize Weatherbit forecast data."""

        hourly: list[Any] = []
        daily: list[Any] = []
        raw_payload: dict[str, Any] = {}

        if Granularity.HOURLY in params.granularity:
            raw_hourly, error = await self._get_json(
                client,
                _HOURLY_URL,
                params={
                    "lat": params.latitude,
                    "lon": params.longitude,
                    "hours": self.config.hours,
                    "units": self.config.units,
                    "key": self.config.api_key,
                },
            )
            if error is not None:
                return error
            if not isinstance(raw_hourly, dict):
                return self._error(
                    ErrorCode.PARSE,
                    "Unexpected Weatherbit hourly payload",
                    raw=raw_hourly,
                )
            raw_payload["hourly"] = raw_hourly
            hourly = [
                _parse_hour(entry, self.config.units)
                for entry in raw_hourly.get("data", [])
                if isinstance(entry, Mapping)
            ]

        if Granularity.DAILY in params.granularity:
            raw_daily, error = await self._get_json(
                client,
                _DAILY_URL,
                params={
                    "lat": params.latitude,
                    "lon": params.longitude,
                    "units": self.config.units,
                    "key": self.config.api_key,
                },
            )
            if error is not None:
                return error
            if not isinstance(raw_daily, dict):
                return self._error(
                    ErrorCode.PARSE,
                    "Unexpected Weatherbit daily payload",
                    raw=raw_daily,
                )
            raw_payload["daily"] = raw_daily
            daily = [
                _parse_day(entry, self.config.units)
                for entry in raw_daily.get("data", [])
                if isinstance(entry, Mapping)
            ]

        return self._success(
            [build_source_forecast(self.provider_id, hourly=hourly, daily=daily)],
            raw=raw_payload if params.include_raw else None,
        )


class _WeatherbitPlugin(BasePlugin[WeatherbitConfig]):
    """Weatherbit plugin facade."""

    config_model = WeatherbitConfig
    instance_cls = _WeatherbitInstance
    _id = ProviderId.WEATHERBIT
    _name = "Weatherbit"


weatherbit_plugin = _WeatherbitPlugin()

__all__ = ["weatherbit_plugin"]

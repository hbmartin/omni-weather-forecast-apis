"""OpenWeather One Call 3.0 adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import Field

from omni_weather_forecast_apis.mapping import OPENWEATHER_CONDITION_MAP, km_from_meters
from omni_weather_forecast_apis.mapping.units import (
    celsius_from_fahrenheit,
    celsius_from_kelvin,
    ms_from_mph,
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
    local_date_from_epoch,
    probability_from_fraction,
)
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    Granularity,
    MinutelyDataPoint,
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    WeatherCondition,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.types.plugin import ProviderConfigModel

if TYPE_CHECKING:
    import httpx2


class OpenWeatherConfig(ProviderConfigModel):
    api_key: str = Field(min_length=1)
    exclude: list[str] | None = Field(
        None,
        description="Blocks to exclude: current, minutely, hourly, daily, alerts",
    )
    units: Literal["standard", "metric", "imperial"] = "metric"


_ONE_CALL_URL = "https://api.openweathermap.org/data/3.0/onecall"
_CAPABILITIES = PluginCapabilities(
    granularity_minutely=True,
    granularity_hourly=True,
    granularity_daily=True,
    max_horizon_minutely_hours=1,
    max_horizon_hourly_hours=48,
    max_horizon_daily_days=8,
    alerts=True,
)


def _normalize_temperature(value: float | None, units: str) -> float | None:
    if value is None:
        return None
    match units:
        case "standard":
            return celsius_from_kelvin(value)
        case "imperial":
            return celsius_from_fahrenheit(value)
        case _:
            return value


def _normalize_wind_speed(value: float | None, units: str) -> float | None:
    if value is None:
        return None
    if units == "imperial":
        return ms_from_mph(value)
    return value


def _sum_present(*values: float | None) -> float | None:
    present_values = [value for value in values if value is not None]
    if not present_values:
        return None
    return sum(present_values)


def _is_daylight(entry: Mapping[str, Any]) -> bool | None:
    dt = entry.get("dt")
    sunrise = entry.get("sunrise")
    sunset = entry.get("sunset")
    if not isinstance(dt, int):
        return None
    if not isinstance(sunrise, int) or not isinstance(sunset, int):
        return None
    return sunrise <= dt < sunset


def _parse_weather_block(
    entry: Mapping[str, Any],
) -> tuple[str | None, int | None, WeatherCondition | None]:
    weather = entry.get("weather")
    if not isinstance(weather, list) or not weather:
        return None, None, None
    first = weather[0]
    if not isinstance(first, Mapping):
        return None, None, None
    description = first.get("description")
    code = first.get("id")
    condition = OPENWEATHER_CONDITION_MAP.get(code) if isinstance(code, int) else None
    return (
        description if isinstance(description, str) else None,
        code if isinstance(code, int) else None,
        condition,
    )


def _parse_hourly_entry(
    entry: Mapping[str, Any],
    *,
    units: str,
) -> WeatherDataPoint:
    description, code, mapped_condition = _parse_weather_block(entry)
    rain = first_present(entry, "rain")
    snow = first_present(entry, "snow")
    visibility_meters = as_float(entry.get("visibility"))
    rain_amount = (
        as_float(rain.get("1h")) if isinstance(rain, Mapping) else as_float(rain)
    )
    snow_amount = (
        as_float(snow.get("1h")) if isinstance(snow, Mapping) else as_float(snow)
    )
    return build_hourly_point(
        entry["dt"],
        temperature=_normalize_temperature(as_float(entry.get("temp")), units),
        apparent_temperature=_normalize_temperature(
            as_float(entry.get("feels_like")),
            units,
        ),
        dew_point=_normalize_temperature(as_float(entry.get("dew_point")), units),
        humidity=as_float(entry.get("humidity")),
        wind_speed=_normalize_wind_speed(as_float(entry.get("wind_speed")), units),
        wind_gust=_normalize_wind_speed(as_float(entry.get("wind_gust")), units),
        wind_direction=as_float(entry.get("wind_deg")),
        pressure_sea=as_float(entry.get("pressure")),
        precipitation=_sum_present(rain_amount, snow_amount),
        precipitation_probability=probability_from_fraction(entry.get("pop")),
        rain=rain_amount,
        snow=snow_amount,
        cloud_cover=as_float(entry.get("clouds")),
        visibility=(
            km_from_meters(visibility_meters) if visibility_meters is not None else None
        ),
        uv_index=as_float(entry.get("uvi")),
        condition=fallback_condition(mapped_condition, description),
        condition_original=description,
        condition_code_original=code,
        is_day=_is_daylight(entry),
    )


def _parse_daily_entry(
    entry: Mapping[str, Any],
    *,
    units: str,
    location_timezone: ZoneInfo,
) -> DailyDataPoint:
    description, _code, mapped_condition = _parse_weather_block(entry)
    temperature = entry.get("temp")
    feels_like = entry.get("feels_like")
    rain_amount = as_float(entry.get("rain"))
    snow_amount = as_float(entry.get("snow"))
    local_date = local_date_from_epoch(entry["dt"], location_timezone)
    return build_daily_point(
        local_date if local_date is not None else entry["dt"],
        temperature_max=_normalize_temperature(
            (
                as_float(temperature.get("max"))
                if isinstance(temperature, Mapping)
                else None
            ),
            units,
        ),
        temperature_min=_normalize_temperature(
            (
                as_float(temperature.get("min"))
                if isinstance(temperature, Mapping)
                else None
            ),
            units,
        ),
        apparent_temperature_max=_normalize_temperature(
            (
                as_float(feels_like.get("day"))
                if isinstance(feels_like, Mapping)
                else None
            ),
            units,
        ),
        apparent_temperature_min=_normalize_temperature(
            (
                as_float(feels_like.get("night"))
                if isinstance(feels_like, Mapping)
                else None
            ),
            units,
        ),
        wind_speed_max=_normalize_wind_speed(as_float(entry.get("wind_speed")), units),
        wind_gust_max=_normalize_wind_speed(as_float(entry.get("wind_gust")), units),
        wind_direction_dominant=as_float(entry.get("wind_deg")),
        precipitation_sum=_sum_present(rain_amount, snow_amount),
        precipitation_probability_max=probability_from_fraction(entry.get("pop")),
        rain_sum=rain_amount,
        snowfall_sum=snow_amount,
        cloud_cover_mean=as_float(entry.get("clouds")),
        uv_index_max=as_float(entry.get("uvi")),
        humidity_mean=as_float(entry.get("humidity")),
        pressure_sea_mean=as_float(entry.get("pressure")),
        condition=fallback_condition(mapped_condition, description),
        summary=description,
        sunrise=entry.get("sunrise"),
        sunset=entry.get("sunset"),
        moonrise=entry.get("moonrise"),
        moonset=entry.get("moonset"),
        moon_phase=as_float(entry.get("moon_phase")),
    )


class _OpenWeatherInstance(BasePluginInstance[OpenWeatherConfig]):
    """Configured OpenWeather adapter."""

    def __init__(self, config: OpenWeatherConfig) -> None:
        super().__init__(ProviderId.OPENWEATHER, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        """Fetch and normalize OpenWeather forecast data."""

        requested_excludes = set(self.config.exclude or [])
        if Granularity.MINUTELY not in params.granularity:
            requested_excludes.add("minutely")
        if Granularity.HOURLY not in params.granularity:
            requested_excludes.add("hourly")
        if Granularity.DAILY not in params.granularity:
            requested_excludes.add("daily")
        raw = await self._get_json_dict(
            client,
            _ONE_CALL_URL,
            params={
                "lat": params.latitude,
                "lon": params.longitude,
                "appid": self.config.api_key,
                "units": self.config.units,
                "lang": params.language,
                "exclude": ",".join(sorted(requested_excludes)),
            },
            payload_name="OpenWeather",
        )
        if isinstance(raw, PluginFetchError):
            return raw

        location_timezone: ZoneInfo | None = None
        if Granularity.DAILY in params.granularity:
            resolved_timezone = await self._resolve_location_timezone(
                params,
                client,
                provider_timezone=raw.get("timezone"),
            )
            if isinstance(resolved_timezone, PluginFetchError):
                return resolved_timezone
            location_timezone = resolved_timezone
        minutely: list[MinutelyDataPoint] = [
            build_minutely_point(
                entry["dt"],
                precipitation_intensity=as_float(entry.get("precipitation")),
                precipitation_probability=probability_from_fraction(entry.get("pop")),
            )
            for entry in raw.get("minutely", [])
            if isinstance(entry, Mapping) and "dt" in entry
        ]
        hourly = [
            _parse_hourly_entry(entry, units=self.config.units)
            for entry in raw.get("hourly", [])
            if isinstance(entry, Mapping) and "dt" in entry
        ]
        daily = (
            [
                _parse_daily_entry(
                    entry,
                    units=self.config.units,
                    location_timezone=location_timezone,
                )
                for entry in raw.get("daily", [])
                if isinstance(entry, Mapping) and "dt" in entry
            ]
            if location_timezone is not None
            else []
        )
        alerts = [
            build_alert(
                sender_name=str(
                    first_present(entry, "sender_name", "sender", "source")
                    or "OpenWeather",
                ),
                event=str(entry.get("event") or "Alert"),
                start=entry["start"],
                end=entry.get("end"),
                description=str(entry.get("description") or ""),
                # One Call alerts carry category tags, not links; there is no URL.
                url=None,
            )
            for entry in raw.get("alerts", [])
            if isinstance(entry, Mapping) and "start" in entry
        ]
        return self._success(
            [
                build_source_forecast(
                    self.provider_id,
                    timezone=(
                        location_timezone.key
                        if location_timezone is not None
                        else params.timezone
                    ),
                    minutely=minutely,
                    hourly=hourly,
                    daily=daily,
                    alerts=alerts,
                ),
            ],
            raw=raw if params.include_raw else None,
        )


class _OpenWeatherPlugin(BasePlugin[OpenWeatherConfig]):
    """OpenWeather plugin facade."""

    config_model = OpenWeatherConfig
    instance_cls = _OpenWeatherInstance
    _id = ProviderId.OPENWEATHER
    _name = "OpenWeather"


openweather_plugin = _OpenWeatherPlugin()

__all__ = ["openweather_plugin"]

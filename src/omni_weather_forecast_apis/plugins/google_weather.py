"""Google Weather (Google Maps Platform Weather API) provider adapter."""

from __future__ import annotations

from datetime import date
from typing import Any, Final

import httpx2
from pydantic import Field

from omni_weather_forecast_apis.mapping import (
    celsius_from_fahrenheit,
    km_from_miles,
    mm_from_inches,
    ms_from_kmh,
    ms_from_mph,
)
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_daily_point,
    build_hourly_point,
    build_source_forecast,
    fallback_condition,
    probability_from_percent_value,
)
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ErrorCode,
    Granularity,
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    WeatherCondition,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.types.plugin import ProviderConfigModel


class GoogleWeatherConfig(ProviderConfigModel):
    api_key: str = Field(min_length=1)
    hours: int = Field(default=48, ge=1, le=240)
    days: int = Field(default=10, ge=1, le=10)


GOOGLE_WEATHER_BASE_URL: Final = "https://weather.googleapis.com/v1"
_HOURS_PAGE_SIZE: Final = 24
_DAYS_PAGE_SIZE: Final = 10
_MAX_PAGES: Final = 15

GOOGLE_CONDITION_MAP: Final[dict[str, WeatherCondition]] = {
    "CLEAR": WeatherCondition.CLEAR,
    "MOSTLY_CLEAR": WeatherCondition.MOSTLY_CLEAR,
    "PARTLY_CLOUDY": WeatherCondition.PARTLY_CLOUDY,
    "MOSTLY_CLOUDY": WeatherCondition.MOSTLY_CLOUDY,
    "CLOUDY": WeatherCondition.OVERCAST,
    "WINDY": WeatherCondition.UNKNOWN,
    "WIND_AND_RAIN": WeatherCondition.RAIN,
    "LIGHT_RAIN_SHOWERS": WeatherCondition.LIGHT_RAIN,
    "CHANCE_OF_SHOWERS": WeatherCondition.LIGHT_RAIN,
    "SCATTERED_SHOWERS": WeatherCondition.LIGHT_RAIN,
    "RAIN_SHOWERS": WeatherCondition.RAIN,
    "HEAVY_RAIN_SHOWERS": WeatherCondition.HEAVY_RAIN,
    "LIGHT_TO_MODERATE_RAIN": WeatherCondition.LIGHT_RAIN,
    "MODERATE_TO_HEAVY_RAIN": WeatherCondition.HEAVY_RAIN,
    "RAIN": WeatherCondition.RAIN,
    "LIGHT_RAIN": WeatherCondition.LIGHT_RAIN,
    "HEAVY_RAIN": WeatherCondition.HEAVY_RAIN,
    "RAIN_PERIODICALLY_HEAVY": WeatherCondition.HEAVY_RAIN,
    "LIGHT_SNOW_SHOWERS": WeatherCondition.LIGHT_SNOW,
    "CHANCE_OF_SNOW_SHOWERS": WeatherCondition.LIGHT_SNOW,
    "SCATTERED_SNOW_SHOWERS": WeatherCondition.LIGHT_SNOW,
    "SNOW_SHOWERS": WeatherCondition.SNOW,
    "HEAVY_SNOW_SHOWERS": WeatherCondition.HEAVY_SNOW,
    "LIGHT_TO_MODERATE_SNOW": WeatherCondition.LIGHT_SNOW,
    "MODERATE_TO_HEAVY_SNOW": WeatherCondition.HEAVY_SNOW,
    "SNOW": WeatherCondition.SNOW,
    "LIGHT_SNOW": WeatherCondition.LIGHT_SNOW,
    "HEAVY_SNOW": WeatherCondition.HEAVY_SNOW,
    "SNOWSTORM": WeatherCondition.HEAVY_SNOW,
    "SNOW_PERIODICALLY_HEAVY": WeatherCondition.HEAVY_SNOW,
    "HEAVY_SNOW_STORM": WeatherCondition.HEAVY_SNOW,
    "BLOWING_SNOW": WeatherCondition.SNOW,
    "RAIN_AND_SNOW": WeatherCondition.SLEET,
    "HAIL": WeatherCondition.HAIL,
    "HAIL_SHOWERS": WeatherCondition.HAIL,
    "THUNDERSTORM": WeatherCondition.THUNDERSTORM,
    "THUNDERSHOWER": WeatherCondition.THUNDERSTORM_RAIN,
    "LIGHT_THUNDERSTORM_RAIN": WeatherCondition.THUNDERSTORM_RAIN,
    "SCATTERED_THUNDERSTORMS": WeatherCondition.THUNDERSTORM,
    "HEAVY_THUNDERSTORM": WeatherCondition.THUNDERSTORM_HEAVY,
}

_MOON_PHASE_MAP: Final[dict[str, float]] = {
    "NEW_MOON": 0.0,
    "WAXING_CRESCENT": 0.125,
    "FIRST_QUARTER": 0.25,
    "WAXING_GIBBOUS": 0.375,
    "FULL_MOON": 0.5,
    "WANING_GIBBOUS": 0.625,
    "LAST_QUARTER": 0.75,
    "WANING_CRESCENT": 0.875,
}

_CAPABILITIES = PluginCapabilities(
    granularity_minutely=False,
    granularity_hourly=True,
    granularity_daily=True,
    max_horizon_hourly_hours=240,
    max_horizon_daily_days=10,
    requires_api_key=True,
    multi_model=False,
    coverage="global",
    alerts=False,
)


def _degrees(block: Any) -> float | None:
    if not isinstance(block, dict):
        return None
    value = as_float(block.get("degrees"))
    if value is not None and block.get("unit") == "FAHRENHEIT":
        return celsius_from_fahrenheit(value)
    return value


def _speed_ms(block: Any) -> float | None:
    if not isinstance(block, dict):
        return None
    value = as_float(block.get("value"))
    if value is None:
        return None
    if block.get("unit") == "MILES_PER_HOUR":
        return ms_from_mph(value)
    return ms_from_kmh(value)


def _qpf_mm(block: Any) -> float | None:
    if not isinstance(block, dict):
        return None
    value = as_float(block.get("quantity"))
    if value is not None and block.get("unit") == "INCHES":
        return mm_from_inches(value)
    return value


def _distance_km(block: Any) -> float | None:
    if not isinstance(block, dict):
        return None
    value = as_float(block.get("distance"))
    if value is not None and block.get("unit") == "MILES":
        return km_from_miles(value)
    return value


def _condition_type(entry: dict[str, Any]) -> str | None:
    block = entry.get("weatherCondition")
    if not isinstance(block, dict):
        return None
    condition_type = block.get("type")
    return condition_type if isinstance(condition_type, str) else None


def _condition_text(entry: dict[str, Any]) -> str | None:
    block = entry.get("weatherCondition")
    if not isinstance(block, dict):
        return None
    description = block.get("description")
    if not isinstance(description, dict):
        return None
    text = description.get("text")
    return text if isinstance(text, str) else None


def _map_condition(entry: dict[str, Any]) -> WeatherCondition | None:
    condition_type = _condition_type(entry)
    mapped = GOOGLE_CONDITION_MAP.get(condition_type) if condition_type else None
    return fallback_condition(mapped, _condition_text(entry))


def _wind_block(entry: dict[str, Any], key: str) -> Any:
    wind = entry.get("wind")
    if not isinstance(wind, dict):
        return None
    return wind.get(key)


def _wind_direction(entry: dict[str, Any]) -> float | None:
    direction = _wind_block(entry, "direction")
    if not isinstance(direction, dict):
        return None
    return as_float(direction.get("degrees"))


def _precipitation_block(entry: dict[str, Any], key: str) -> Any:
    precipitation = entry.get("precipitation")
    if not isinstance(precipitation, dict):
        return None
    return precipitation.get(key)


def _precipitation_probability(entry: dict[str, Any]) -> float | None:
    probability = _precipitation_block(entry, "probability")
    if not isinstance(probability, dict):
        return None
    return probability_from_percent_value(probability.get("percent"))


def _interval_start(entry: dict[str, Any]) -> str | None:
    interval = entry.get("interval")
    if not isinstance(interval, dict):
        return None
    start = interval.get("startTime")
    return start if isinstance(start, str) else None


def _optional_max(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _optional_mean(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _optional_sum(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


class GoogleWeatherInstance(BasePluginInstance[GoogleWeatherConfig]):
    """Configured Google Weather provider."""

    def __init__(self, config: GoogleWeatherConfig) -> None:
        super().__init__(ProviderId.GOOGLE_WEATHER, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        hourly: list[WeatherDataPoint] = []
        daily: list[DailyDataPoint] = []
        raw: dict[str, Any] = {}

        try:
            if Granularity.HOURLY in params.granularity:
                entries, error = await self._fetch_paged(
                    client,
                    endpoint="forecast/hours:lookup",
                    params=params,
                    item_key="forecastHours",
                    count_param="hours",
                    count=self.config.hours,
                    page_size=min(_HOURS_PAGE_SIZE, self.config.hours),
                )
                if error is not None:
                    return error
                hourly = [
                    point
                    for entry in entries
                    if (point := self._parse_hour(entry)) is not None
                ]
                if params.include_raw:
                    raw["forecastHours"] = entries

            if Granularity.DAILY in params.granularity:
                entries, error = await self._fetch_paged(
                    client,
                    endpoint="forecast/days:lookup",
                    params=params,
                    item_key="forecastDays",
                    count_param="days",
                    count=self.config.days,
                    page_size=min(_DAYS_PAGE_SIZE, self.config.days),
                )
                if error is not None:
                    return error
                daily = [
                    point
                    for entry in entries
                    if (point := self._parse_day(entry)) is not None
                ]
                if params.include_raw:
                    raw["forecastDays"] = entries
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse Google Weather payload: {exc}",
            )

        forecasts = [
            build_source_forecast(
                ProviderId.GOOGLE_WEATHER,
                hourly=hourly,
                daily=daily,
            ),
        ]
        return self._success(forecasts, raw=raw if params.include_raw else None)

    async def _fetch_paged(
        self,
        client: httpx2.AsyncClient,
        *,
        endpoint: str,
        params: PluginFetchParams,
        item_key: str,
        count_param: str,
        count: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], PluginFetchError | None]:
        entries: list[dict[str, Any]] = []
        page_token: str | None = None
        for _page in range(_MAX_PAGES):
            request_params: dict[str, Any] = {
                "key": self.config.api_key,
                "location.latitude": params.latitude,
                "location.longitude": params.longitude,
                "unitsSystem": "METRIC",
                "languageCode": params.language,
                count_param: count,
                "pageSize": page_size,
            }
            if page_token is not None:
                request_params["pageToken"] = page_token
            payload = await self._get_json_dict(
                client,
                f"{GOOGLE_WEATHER_BASE_URL}/{endpoint}",
                params=request_params,
                payload_name="Google Weather",
            )
            if isinstance(payload, PluginFetchError):
                return [], payload
            items = payload.get(item_key)
            if isinstance(items, list):
                entries.extend(item for item in items if isinstance(item, dict))
            next_token = payload.get("nextPageToken")
            if (
                not isinstance(next_token, str)
                or not next_token
                or len(entries) >= count
            ):
                break
            page_token = next_token
        return entries[:count], None

    def _parse_hour(self, entry: dict[str, Any]) -> WeatherDataPoint | None:
        start = _interval_start(entry)
        if start is None:
            return None
        is_daytime = entry.get("isDaytime")
        pressure = entry.get("airPressure")
        return build_hourly_point(
            start,
            temperature=_degrees(entry.get("temperature")),
            apparent_temperature=_degrees(entry.get("feelsLikeTemperature")),
            dew_point=_degrees(entry.get("dewPoint")),
            humidity=as_float(entry.get("relativeHumidity")),
            wind_speed=_speed_ms(_wind_block(entry, "speed")),
            wind_gust=_speed_ms(_wind_block(entry, "gust")),
            wind_direction=_wind_direction(entry),
            pressure_sea=(
                as_float(pressure.get("meanSeaLevelMillibars"))
                if isinstance(pressure, dict)
                else None
            ),
            precipitation=_qpf_mm(_precipitation_block(entry, "qpf")),
            precipitation_probability=_precipitation_probability(entry),
            cloud_cover=as_float(entry.get("cloudCover")),
            visibility=_distance_km(entry.get("visibility")),
            uv_index=as_float(entry.get("uvIndex")),
            condition=_map_condition(entry),
            condition_original=_condition_text(entry),
            condition_code_original=_condition_type(entry),
            is_day=is_daytime if isinstance(is_daytime, bool) else None,
        )

    def _parse_day(self, entry: dict[str, Any]) -> DailyDataPoint | None:
        date_value = self._display_date(entry)
        if date_value is None:
            return None
        day_part = entry.get("daytimeForecast")
        night_part = entry.get("nighttimeForecast")
        day_part = day_part if isinstance(day_part, dict) else {}
        night_part = night_part if isinstance(night_part, dict) else {}
        sun_events = entry.get("sunEvents")
        sun_events = sun_events if isinstance(sun_events, dict) else {}
        moon_events = entry.get("moonEvents")
        moon_events = moon_events if isinstance(moon_events, dict) else {}
        moon_phase_name = moon_events.get("moonPhase")

        return build_daily_point(
            date_value,
            temperature_max=_degrees(entry.get("maxTemperature")),
            temperature_min=_degrees(entry.get("minTemperature")),
            apparent_temperature_max=_degrees(entry.get("feelsLikeMaxTemperature")),
            apparent_temperature_min=_degrees(entry.get("feelsLikeMinTemperature")),
            wind_speed_max=_optional_max(
                _speed_ms(_wind_block(day_part, "speed")),
                _speed_ms(_wind_block(night_part, "speed")),
            ),
            wind_gust_max=_optional_max(
                _speed_ms(_wind_block(day_part, "gust")),
                _speed_ms(_wind_block(night_part, "gust")),
            ),
            wind_direction_dominant=_wind_direction(day_part),
            precipitation_sum=_optional_sum(
                _qpf_mm(_precipitation_block(day_part, "qpf")),
                _qpf_mm(_precipitation_block(night_part, "qpf")),
            ),
            precipitation_probability_max=_optional_max(
                _precipitation_probability(day_part),
                _precipitation_probability(night_part),
            ),
            cloud_cover_mean=_optional_mean(
                as_float(day_part.get("cloudCover")),
                as_float(night_part.get("cloudCover")),
            ),
            uv_index_max=_optional_max(
                as_float(day_part.get("uvIndex")),
                as_float(night_part.get("uvIndex")),
            ),
            humidity_mean=_optional_mean(
                as_float(day_part.get("relativeHumidity")),
                as_float(night_part.get("relativeHumidity")),
            ),
            condition=_map_condition(day_part) or _map_condition(night_part),
            summary=_condition_text(day_part),
            sunrise=sun_events.get("sunriseTime"),
            sunset=sun_events.get("sunsetTime"),
            moonrise=_first_time(moon_events.get("moonriseTimes")),
            moonset=_first_time(moon_events.get("moonsetTimes")),
            moon_phase=(
                _MOON_PHASE_MAP.get(moon_phase_name)
                if isinstance(moon_phase_name, str)
                else None
            ),
        )

    @staticmethod
    def _display_date(entry: dict[str, Any]) -> date | None:
        display_date = entry.get("displayDate")
        if not isinstance(display_date, dict):
            return None
        year = display_date.get("year")
        month = display_date.get("month")
        day = display_date.get("day")
        if (
            not isinstance(year, int)
            or not isinstance(month, int)
            or not isinstance(day, int)
        ):
            return None
        try:
            return date(year, month, day)
        except (ValueError,):  # noqa: B013
            return None


def _first_time(values: Any) -> str | None:
    if isinstance(values, list) and values and isinstance(values[0], str):
        return values[0]
    return None


class GoogleWeatherPlugin(BasePlugin[GoogleWeatherConfig]):
    """Google Weather plugin facade."""

    config_model = GoogleWeatherConfig
    instance_cls = GoogleWeatherInstance
    _id = ProviderId.GOOGLE_WEATHER
    _name = "Google Weather"


google_weather_plugin = GoogleWeatherPlugin()

__all__ = ["GoogleWeatherConfig", "GoogleWeatherInstance", "google_weather_plugin"]

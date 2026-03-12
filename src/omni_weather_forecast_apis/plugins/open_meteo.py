"""Open-Meteo plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.mapping.conditions import WMO_CODE_MAP
from omni_weather_forecast_apis.types.plugin import (
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
)
from omni_weather_forecast_apis.types.schema import (
    DailyDataPoint,
    ErrorCode,
    Granularity,
    MinutelyDataPoint,
    ModelSource,
    ProviderId,
    SourceForecast,
    WeatherCondition,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.utils.time_helpers import parse_iso_datetime


class OpenMeteoConfig(BaseModel):
    api_key: str | None = None
    models: list[str] = Field(
        default=["best_match"],
        description="Weather models to request.",
    )
    extra_hourly_vars: list[str] | None = None
    extra_daily_vars: list[str] | None = None


_DEFAULT_HOURLY = [
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
    "snow_depth",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "visibility",
    "uv_index",
    "weather_code",
    "is_day",
]

_DEFAULT_DAILY = [
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
    "uv_index_max",
    "weather_code",
    "sunrise",
    "sunset",
    "daylight_duration",
]

_DEFAULT_MINUTELY = [
    "precipitation",
]


class OpenMeteoPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.OPEN_METEO

    @property
    def name(self) -> str:
        return "Open-Meteo"

    def validate_config(self, config: dict[str, Any]) -> OpenMeteoConfig:
        return OpenMeteoConfig(**config)

    async def initialize(self, config: Any) -> OpenMeteoInstance:
        return OpenMeteoInstance(config)


class OpenMeteoInstance:
    def __init__(self, config: OpenMeteoConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.OPEN_METEO

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=True,
            granularity_hourly=True,
            granularity_daily=True,
            max_horizon_minutely_hours=1,
            max_horizon_hourly_hours=384,
            max_horizon_daily_days=16,
            requires_api_key=False,
            multi_model=True,
            coverage="global",
            alerts=False,
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        try:
            base_url = (
                "https://customer-api.open-meteo.com/v1/forecast"
                if self._config.api_key
                else "https://api.open-meteo.com/v1/forecast"
            )
            query: dict[str, Any] = {
                "latitude": params.latitude,
                "longitude": params.longitude,
                "timezone": "UTC",
                "timeformat": "iso8601",
            }
            if self._config.api_key:
                query["apikey"] = self._config.api_key

            if len(self._config.models) > 1 or self._config.models != ["best_match"]:
                query["models"] = ",".join(self._config.models)

            hourly_vars = list(_DEFAULT_HOURLY)
            if self._config.extra_hourly_vars:
                hourly_vars.extend(self._config.extra_hourly_vars)
            daily_vars = list(_DEFAULT_DAILY)
            if self._config.extra_daily_vars:
                daily_vars.extend(self._config.extra_daily_vars)

            if Granularity.HOURLY in params.granularity:
                query["hourly"] = ",".join(hourly_vars)
            if Granularity.DAILY in params.granularity:
                query["daily"] = ",".join(daily_vars)
            if Granularity.MINUTELY in params.granularity:
                query["minutely_15"] = ",".join(_DEFAULT_MINUTELY)

            resp = await client.get(base_url, params=query)

            if resp.status_code == 401:
                return PluginFetchError(
                    code=ErrorCode.AUTH_FAILED,
                    message="Invalid API key",
                    http_status=401,
                )
            if resp.status_code == 429:
                return PluginFetchError(
                    code=ErrorCode.RATE_LIMITED,
                    message="Rate limited",
                    http_status=429,
                )
            if resp.status_code != 200:
                return PluginFetchError(
                    code=ErrorCode.UNKNOWN,
                    message=f"HTTP {resp.status_code}",
                    http_status=resp.status_code,
                )

            data = resp.json()
            return self._parse_response(data, params)

        except httpx.TimeoutException:
            return PluginFetchError(code=ErrorCode.TIMEOUT, message="Request timed out")
        except (httpx.HTTPError, OSError) as e:
            return PluginFetchError(code=ErrorCode.NETWORK, message=str(e))
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    def _parse_response(
        self,
        data: dict[str, Any],
        params: PluginFetchParams,
    ) -> PluginFetchResult:
        try:
            forecasts: list[SourceForecast] = []

            for model_name in self._config.models:
                source = ModelSource(provider=ProviderId.OPEN_METEO, model=model_name)
                hourly = self._parse_hourly(data, model_name)
                daily = self._parse_daily(data, model_name)
                minutely = self._parse_minutely(data, model_name)

                forecasts.append(
                    SourceForecast(
                        source=source,
                        minutely=minutely,
                        hourly=hourly,
                        daily=daily,
                    ),
                )

            raw = data if params.include_raw else None
            return PluginFetchSuccess(forecasts=forecasts, raw=raw)
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    def _get_section(
        self,
        data: dict[str, Any],
        section: str,
        model: str,
    ) -> dict[str, Any] | None:
        """Get a data section, handling multi-model key suffixes."""
        if model != "best_match" and f"{section}_{model}" in data:
            return data[f"{section}_{model}"]
        return data.get(section)

    @staticmethod
    def _array_get(section: dict[str, Any], key: str, idx: int) -> Any:
        """Get value at index from a parallel array, returning None if missing."""
        arr = section.get(key, [])
        return arr[idx] if idx < len(arr) else None

    def _parse_minutely(
        self,
        data: dict[str, Any],
        model: str,
    ) -> list[MinutelyDataPoint]:
        section = self._get_section(data, "minutely_15", model)
        if not section:
            return []
        times = section.get("time", [])
        precip = section.get("precipitation", [])
        result: list[MinutelyDataPoint] = []
        for i, t in enumerate(times):
            dt = parse_iso_datetime(t)
            result.append(
                MinutelyDataPoint(
                    timestamp=dt,
                    timestamp_unix=int(dt.timestamp()),
                    precipitation_intensity=precip[i] if i < len(precip) else None,
                ),
            )
        return result

    def _parse_hourly(self, data: dict[str, Any], model: str) -> list[WeatherDataPoint]:
        section = self._get_section(data, "hourly", model)
        if not section:
            return []

        times = section.get("time", [])
        result: list[WeatherDataPoint] = []

        g = self._array_get
        for i, t in enumerate(times):
            dt = parse_iso_datetime(t)
            wmo = g(section, "weather_code", i)
            is_day_val = g(section, "is_day", i)
            precip_prob = g(section, "precipitation_probability", i)

            result.append(
                WeatherDataPoint(
                    timestamp=dt,
                    timestamp_unix=int(dt.timestamp()),
                    temperature=g(section, "temperature_2m", i),
                    apparent_temperature=g(section, "apparent_temperature", i),
                    dew_point=g(section, "dew_point_2m", i),
                    humidity=g(section, "relative_humidity_2m", i),
                    wind_speed=g(section, "wind_speed_10m", i),
                    wind_gust=g(section, "wind_gusts_10m", i),
                    wind_direction=g(section, "wind_direction_10m", i),
                    pressure_sea=g(section, "pressure_msl", i),
                    pressure_surface=g(section, "surface_pressure", i),
                    precipitation=g(section, "precipitation", i),
                    precipitation_probability=(
                        precip_prob / 100.0 if precip_prob is not None else None
                    ),
                    rain=g(section, "rain", i),
                    snow=g(section, "snowfall", i),
                    snow_depth=g(section, "snow_depth", i),
                    cloud_cover=g(section, "cloud_cover", i),
                    cloud_cover_low=g(section, "cloud_cover_low", i),
                    cloud_cover_mid=g(section, "cloud_cover_mid", i),
                    cloud_cover_high=g(section, "cloud_cover_high", i),
                    visibility=g(section, "visibility", i),
                    uv_index=g(section, "uv_index", i),
                    condition=(
                        WMO_CODE_MAP.get(wmo, WeatherCondition.UNKNOWN)
                        if wmo is not None
                        else None
                    ),
                    condition_code_original=wmo,
                    is_day=bool(is_day_val) if is_day_val is not None else None,
                ),
            )
        return result

    def _parse_daily(self, data: dict[str, Any], model: str) -> list[DailyDataPoint]:
        section = self._get_section(data, "daily", model)
        if not section:
            return []

        times = section.get("time", [])
        result: list[DailyDataPoint] = []

        g = self._array_get
        for i, t in enumerate(times):
            dt = parse_iso_datetime(t)
            wmo = g(section, "weather_code", i)
            sunrise_str = g(section, "sunrise", i)
            sunset_str = g(section, "sunset", i)
            precip_prob = g(section, "precipitation_probability_max", i)

            result.append(
                DailyDataPoint(
                    date=dt.date(),
                    temperature_max=g(section, "temperature_2m_max", i),
                    temperature_min=g(section, "temperature_2m_min", i),
                    apparent_temperature_max=g(section, "apparent_temperature_max", i),
                    apparent_temperature_min=g(section, "apparent_temperature_min", i),
                    wind_speed_max=g(section, "wind_speed_10m_max", i),
                    wind_gust_max=g(section, "wind_gusts_10m_max", i),
                    wind_direction_dominant=g(
                        section,
                        "wind_direction_10m_dominant",
                        i,
                    ),
                    precipitation_sum=g(section, "precipitation_sum", i),
                    precipitation_probability_max=(
                        precip_prob / 100.0 if precip_prob is not None else None
                    ),
                    rain_sum=g(section, "rain_sum", i),
                    snowfall_sum=g(section, "snowfall_sum", i),
                    uv_index_max=g(section, "uv_index_max", i),
                    condition=(
                        WMO_CODE_MAP.get(wmo, WeatherCondition.UNKNOWN)
                        if wmo is not None
                        else None
                    ),
                    sunrise=parse_iso_datetime(sunrise_str) if sunrise_str else None,
                    sunset=parse_iso_datetime(sunset_str) if sunset_str else None,
                    daylight_duration=g(section, "daylight_duration", i),
                ),
            )
        return result


open_meteo_plugin = OpenMeteoPlugin()

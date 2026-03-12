"""Pirate Weather plugin (Dark Sky API format)."""

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
from omni_weather_forecast_apis.utils.time_helpers import datetime_from_unix


class PirateWeatherConfig(BaseModel):
    api_key: str = Field(min_length=1)
    extend_hourly: bool = Field(
        default=False,
        description="Extend hourly forecast to 168 hours",
    )
    version: str = "2"


_ICON_MAP: dict[str, WeatherCondition] = {
    "clear-day": WeatherCondition.CLEAR,
    "clear-night": WeatherCondition.CLEAR,
    "rain": WeatherCondition.RAIN,
    "snow": WeatherCondition.SNOW,
    "sleet": WeatherCondition.SLEET,
    "wind": WeatherCondition.UNKNOWN,
    "fog": WeatherCondition.FOG,
    "cloudy": WeatherCondition.OVERCAST,
    "partly-cloudy-day": WeatherCondition.PARTLY_CLOUDY,
    "partly-cloudy-night": WeatherCondition.PARTLY_CLOUDY,
    "hail": WeatherCondition.HAIL,
    "thunderstorm": WeatherCondition.THUNDERSTORM,
    "tornado": WeatherCondition.TORNADO,
}


class PirateWeatherPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.PIRATE_WEATHER

    @property
    def name(self) -> str:
        return "Pirate Weather"

    def validate_config(self, config: dict[str, Any]) -> PirateWeatherConfig:
        return PirateWeatherConfig(**config)

    async def initialize(self, config: Any) -> PirateWeatherInstance:
        return PirateWeatherInstance(config)


class PirateWeatherInstance:
    def __init__(self, config: PirateWeatherConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.PIRATE_WEATHER

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=True,
            granularity_hourly=True,
            granularity_daily=True,
            max_horizon_minutely_hours=1,
            max_horizon_hourly_hours=168 if self._config.extend_hourly else 48,
            max_horizon_daily_days=8,
            requires_api_key=True,
            multi_model=False,
            coverage="global",
            alerts=True,
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        try:
            exclude = self._build_exclude(params.granularity)
            url = (
                f"https://api.pirateweather.net/forecast/"
                f"{self._config.api_key}/{params.latitude},{params.longitude}"
            )
            query: dict[str, str] = {"units": "si", "version": self._config.version}
            if exclude:
                query["exclude"] = ",".join(exclude)
            if self._config.extend_hourly:
                query["extend"] = "hourly"

            resp = await client.get(url, params=query)

            if resp.status_code in (401, 403):
                return PluginFetchError(
                    code=ErrorCode.AUTH_FAILED,
                    message="Invalid API key",
                    http_status=resp.status_code,
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

    def _build_exclude(self, granularity: list[Granularity]) -> list[str]:
        exclude = ["currently"]
        if Granularity.MINUTELY not in granularity:
            exclude.append("minutely")
        if Granularity.HOURLY not in granularity:
            exclude.append("hourly")
        if Granularity.DAILY not in granularity:
            exclude.append("daily")
        return exclude

    def _parse_response(
        self,
        data: dict[str, Any],
        params: PluginFetchParams,
    ) -> PluginFetchResult:
        try:
            source = ModelSource(
                provider=ProviderId.PIRATE_WEATHER,
                model="pirate_weather",
            )
            minutely = self._parse_minutely(data.get("minutely", {}).get("data", []))
            hourly = self._parse_hourly(data.get("hourly", {}).get("data", []))
            daily = self._parse_daily(data.get("daily", {}).get("data", []))

            forecast = SourceForecast(
                source=source,
                minutely=minutely,
                hourly=hourly,
                daily=daily,
            )
            raw = data if params.include_raw else None
            return PluginFetchSuccess(forecasts=[forecast], raw=raw)
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    def _parse_minutely(self, items: list[dict[str, Any]]) -> list[MinutelyDataPoint]:
        result: list[MinutelyDataPoint] = []
        for item in items:
            ts = item["time"]
            result.append(
                MinutelyDataPoint(
                    timestamp=datetime_from_unix(ts),
                    timestamp_unix=ts,
                    precipitation_intensity=item.get("precipIntensity"),
                    precipitation_probability=item.get("precipProbability"),
                ),
            )
        return result

    def _parse_hourly(self, items: list[dict[str, Any]]) -> list[WeatherDataPoint]:
        result: list[WeatherDataPoint] = []
        for item in items:
            ts = item["time"]
            icon = item.get("icon", "")
            wmo = item.get("weatherCode")

            condition = (
                WMO_CODE_MAP.get(wmo, WeatherCondition.UNKNOWN)
                if wmo is not None
                else _ICON_MAP.get(icon, WeatherCondition.UNKNOWN)
            )

            result.append(
                WeatherDataPoint(
                    timestamp=datetime_from_unix(ts),
                    timestamp_unix=ts,
                    temperature=item.get("temperature"),
                    apparent_temperature=item.get("apparentTemperature"),
                    dew_point=item.get("dewPoint"),
                    humidity=(
                        item["humidity"] * 100
                        if item.get("humidity") is not None
                        else None
                    ),
                    wind_speed=item.get("windSpeed"),
                    wind_gust=item.get("windGust"),
                    wind_direction=item.get("windBearing"),
                    pressure_sea=item.get("pressure"),
                    precipitation=item.get("precipIntensity"),
                    precipitation_probability=item.get("precipProbability"),
                    cloud_cover=(
                        item["cloudCover"] * 100
                        if item.get("cloudCover") is not None
                        else None
                    ),
                    visibility=item.get("visibility"),
                    uv_index=item.get("uvIndex"),
                    condition=condition,
                    condition_original=item.get("summary"),
                    condition_code_original=icon,
                ),
            )
        return result

    def _parse_daily(self, items: list[dict[str, Any]]) -> list[DailyDataPoint]:
        result: list[DailyDataPoint] = []
        for item in items:
            ts = item["time"]
            dt = datetime_from_unix(ts)
            icon = item.get("icon", "")
            wmo = item.get("weatherCode")

            condition = (
                WMO_CODE_MAP.get(wmo, WeatherCondition.UNKNOWN)
                if wmo is not None
                else _ICON_MAP.get(icon, WeatherCondition.UNKNOWN)
            )

            sunrise_ts = item.get("sunriseTime")
            sunset_ts = item.get("sunsetTime")

            result.append(
                DailyDataPoint(
                    date=dt.date(),
                    temperature_max=item.get("temperatureMax"),
                    temperature_min=item.get("temperatureMin"),
                    apparent_temperature_max=item.get("apparentTemperatureMax"),
                    apparent_temperature_min=item.get("apparentTemperatureMin"),
                    wind_speed_max=item.get("windSpeed"),
                    wind_gust_max=item.get("windGust"),
                    wind_direction_dominant=item.get("windBearing"),
                    precipitation_sum=item.get("precipIntensity"),
                    precipitation_probability_max=item.get("precipProbability"),
                    cloud_cover_mean=(
                        item["cloudCover"] * 100
                        if item.get("cloudCover") is not None
                        else None
                    ),
                    uv_index_max=item.get("uvIndex"),
                    humidity_mean=(
                        item["humidity"] * 100
                        if item.get("humidity") is not None
                        else None
                    ),
                    pressure_sea_mean=item.get("pressure"),
                    condition=condition,
                    summary=item.get("summary"),
                    sunrise=datetime_from_unix(sunrise_ts) if sunrise_ts else None,
                    sunset=datetime_from_unix(sunset_ts) if sunset_ts else None,
                    moon_phase=item.get("moonPhase"),
                ),
            )
        return result


pirate_weather_plugin = PirateWeatherPlugin()

"""OpenWeather One Call 3.0 plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.mapping.conditions import OPENWEATHER_CONDITION_MAP
from omni_weather_forecast_apis.mapping.units import km_from_meters, safe_convert
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


class OpenWeatherConfig(BaseModel):
    api_key: str = Field(min_length=1)
    exclude: list[str] | None = Field(
        None,
        description="Blocks to exclude: current, minutely, hourly, daily, alerts",
    )
    units: str = "metric"


class OpenWeatherPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.OPENWEATHER

    @property
    def name(self) -> str:
        return "OpenWeather"

    def validate_config(self, config: dict[str, Any]) -> OpenWeatherConfig:
        return OpenWeatherConfig(**config)

    async def initialize(self, config: Any) -> OpenWeatherInstance:
        return OpenWeatherInstance(config)


class OpenWeatherInstance:
    def __init__(self, config: OpenWeatherConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.OPENWEATHER

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=True,
            granularity_hourly=True,
            granularity_daily=True,
            max_horizon_minutely_hours=1,
            max_horizon_hourly_hours=48,
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
            url = "https://api.openweathermap.org/data/3.0/onecall"
            query: dict[str, Any] = {
                "lat": params.latitude,
                "lon": params.longitude,
                "appid": self._config.api_key,
                "units": self._config.units,
            }
            if exclude:
                query["exclude"] = ",".join(exclude)

            resp = await client.get(url, params=query)

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

    def _build_exclude(self, granularity: list[Granularity]) -> list[str]:
        exclude = ["current"]
        if self._config.exclude:
            return self._config.exclude
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
            source = ModelSource(provider=ProviderId.OPENWEATHER, model="onecall_3.0")
            minutely = self._parse_minutely(data.get("minutely", []))
            hourly = self._parse_hourly(data.get("hourly", []))
            daily = self._parse_daily(data.get("daily", []))

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
            ts = item["dt"]
            result.append(
                MinutelyDataPoint(
                    timestamp=datetime_from_unix(ts),
                    timestamp_unix=ts,
                    precipitation_intensity=item.get("precipitation"),
                ),
            )
        return result

    def _parse_hourly(self, items: list[dict[str, Any]]) -> list[WeatherDataPoint]:
        result: list[WeatherDataPoint] = []
        for item in items:
            ts = item["dt"]
            weather = item.get("weather", [{}])[0] if item.get("weather") else {}
            condition_id = weather.get("id")
            result.append(
                WeatherDataPoint(
                    timestamp=datetime_from_unix(ts),
                    timestamp_unix=ts,
                    temperature=item.get("temp"),
                    apparent_temperature=item.get("feels_like"),
                    dew_point=item.get("dew_point"),
                    humidity=item.get("humidity"),
                    wind_speed=item.get("wind_speed"),
                    wind_gust=item.get("wind_gust"),
                    wind_direction=item.get("wind_deg"),
                    pressure_sea=item.get("pressure"),
                    precipitation=(
                        item.get("rain", {}).get("1h")
                        if isinstance(item.get("rain"), dict)
                        else None
                    ),
                    precipitation_probability=item.get("pop"),
                    snow=(
                        item.get("snow", {}).get("1h")
                        if isinstance(item.get("snow"), dict)
                        else None
                    ),
                    cloud_cover=item.get("clouds"),
                    visibility=safe_convert(item.get("visibility"), km_from_meters),
                    uv_index=item.get("uvi"),
                    condition=(
                        OPENWEATHER_CONDITION_MAP.get(
                            condition_id,
                            WeatherCondition.UNKNOWN,
                        )
                        if condition_id
                        else None
                    ),
                    condition_original=weather.get("description"),
                    condition_code_original=condition_id,
                ),
            )
        return result

    def _parse_daily(self, items: list[dict[str, Any]]) -> list[DailyDataPoint]:
        result: list[DailyDataPoint] = []
        for item in items:
            ts = item["dt"]
            dt = datetime_from_unix(ts)
            weather = item.get("weather", [{}])[0] if item.get("weather") else {}
            condition_id = weather.get("id")
            temp = item.get("temp", {})

            sunrise_ts = item.get("sunrise")
            sunset_ts = item.get("sunset")
            moonrise_ts = item.get("moonrise")
            moonset_ts = item.get("moonset")

            result.append(
                DailyDataPoint(
                    date=dt.date(),
                    temperature_max=temp.get("max"),
                    temperature_min=temp.get("min"),
                    wind_speed_max=item.get("wind_speed"),
                    wind_gust_max=item.get("wind_gust"),
                    wind_direction_dominant=item.get("wind_deg"),
                    precipitation_sum=item.get("rain"),
                    precipitation_probability_max=item.get("pop"),
                    snowfall_sum=item.get("snow"),
                    cloud_cover_mean=item.get("clouds"),
                    uv_index_max=item.get("uvi"),
                    humidity_mean=item.get("humidity"),
                    pressure_sea_mean=item.get("pressure"),
                    condition=(
                        OPENWEATHER_CONDITION_MAP.get(
                            condition_id,
                            WeatherCondition.UNKNOWN,
                        )
                        if condition_id
                        else None
                    ),
                    summary=weather.get("description"),
                    sunrise=datetime_from_unix(sunrise_ts) if sunrise_ts else None,
                    sunset=datetime_from_unix(sunset_ts) if sunset_ts else None,
                    moonrise=datetime_from_unix(moonrise_ts) if moonrise_ts else None,
                    moonset=datetime_from_unix(moonset_ts) if moonset_ts else None,
                    moon_phase=item.get("moon_phase"),
                ),
            )
        return result


openweather_plugin = OpenWeatherPlugin()

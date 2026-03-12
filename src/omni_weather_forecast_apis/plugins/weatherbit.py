"""Weatherbit plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.mapping.conditions import WEATHERBIT_CONDITION_MAP
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
    ModelSource,
    ProviderId,
    SourceForecast,
    WeatherCondition,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.utils.time_helpers import parse_iso_datetime


class WeatherbitConfig(BaseModel):
    api_key: str = Field(min_length=1)
    hours: int = Field(default=48, ge=1, le=240)
    units: str = "M"


class WeatherbitPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.WEATHERBIT

    @property
    def name(self) -> str:
        return "Weatherbit"

    def validate_config(self, config: dict[str, Any]) -> WeatherbitConfig:
        return WeatherbitConfig(**config)

    async def initialize(self, config: Any) -> WeatherbitInstance:
        return WeatherbitInstance(config)


class WeatherbitInstance:
    def __init__(self, config: WeatherbitConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.WEATHERBIT

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=False,
            granularity_hourly=True,
            granularity_daily=True,
            max_horizon_hourly_hours=240,
            max_horizon_daily_days=16,
            requires_api_key=True,
            multi_model=False,
            coverage="global",
            alerts=False,
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        try:
            hourly: list[WeatherDataPoint] = []
            daily: list[DailyDataPoint] = []
            raw_responses: list[Any] = []

            if Granularity.HOURLY in params.granularity:
                result = await self._fetch_hourly(params, client)
                if isinstance(result, PluginFetchError):
                    return result
                hourly, raw_h = result
                if raw_h:
                    raw_responses.append(raw_h)

            if Granularity.DAILY in params.granularity:
                result = await self._fetch_daily(params, client)
                if isinstance(result, PluginFetchError):
                    return result
                daily, raw_d = result
                if raw_d:
                    raw_responses.append(raw_d)

            source = ModelSource(provider=ProviderId.WEATHERBIT, model="weatherbit")
            forecast = SourceForecast(source=source, hourly=hourly, daily=daily)
            raw = raw_responses if params.include_raw else None
            return PluginFetchSuccess(forecasts=[forecast], raw=raw)

        except httpx.TimeoutException:
            return PluginFetchError(code=ErrorCode.TIMEOUT, message="Request timed out")
        except (httpx.HTTPError, OSError) as e:
            return PluginFetchError(code=ErrorCode.NETWORK, message=str(e))
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    async def _fetch_hourly(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchError | tuple[list[WeatherDataPoint], Any]:
        url = "https://api.weatherbit.io/v2.0/forecast/hourly"
        query: dict[str, Any] = {
            "key": self._config.api_key,
            "lat": params.latitude,
            "lon": params.longitude,
            "hours": self._config.hours,
            "units": self._config.units,
        }
        resp = await client.get(url, params=query)
        error = self._check_errors(resp)
        if error:
            return error

        data = resp.json()
        items = data.get("data", [])
        hourly: list[WeatherDataPoint] = []

        for item in items:
            ts_str = item.get("timestamp_utc", "")
            dt = parse_iso_datetime(ts_str)
            weather = item.get("weather", {})
            code = weather.get("code")

            hourly.append(
                WeatherDataPoint(
                    timestamp=dt,
                    timestamp_unix=item.get("ts", int(dt.timestamp())),
                    temperature=item.get("temp"),
                    apparent_temperature=item.get("app_temp"),
                    dew_point=item.get("dewpt"),
                    humidity=item.get("rh"),
                    wind_speed=item.get("wind_spd"),
                    wind_gust=item.get("wind_gust_spd"),
                    wind_direction=item.get("wind_dir"),
                    pressure_sea=item.get("slp"),
                    pressure_surface=item.get("pres"),
                    precipitation=item.get("precip"),
                    precipitation_probability=(
                        item["pop"] / 100.0 if item.get("pop") is not None else None
                    ),
                    snow=item.get("snow"),
                    snow_depth=item.get("snow_depth"),
                    cloud_cover=item.get("clouds"),
                    cloud_cover_low=item.get("clouds_low"),
                    cloud_cover_mid=item.get("clouds_mid"),
                    cloud_cover_high=item.get("clouds_hi"),
                    visibility=item.get("vis"),
                    uv_index=item.get("uv"),
                    solar_radiation_ghi=item.get("ghi"),
                    solar_radiation_dni=item.get("dni"),
                    solar_radiation_dhi=item.get("dhi"),
                    condition=(
                        WEATHERBIT_CONDITION_MAP.get(code, WeatherCondition.UNKNOWN)
                        if code
                        else None
                    ),
                    condition_original=weather.get("description"),
                    condition_code_original=code,
                    is_day=item.get("pod") == "d" if item.get("pod") else None,
                ),
            )

        raw = data if params.include_raw else None
        return hourly, raw

    async def _fetch_daily(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchError | tuple[list[DailyDataPoint], Any]:
        url = "https://api.weatherbit.io/v2.0/forecast/daily"
        query: dict[str, Any] = {
            "key": self._config.api_key,
            "lat": params.latitude,
            "lon": params.longitude,
            "units": self._config.units,
        }
        resp = await client.get(url, params=query)
        error = self._check_errors(resp)
        if error:
            return error

        data = resp.json()
        items = data.get("data", [])
        daily: list[DailyDataPoint] = []

        for item in items:
            date_str = item.get("datetime", "")
            dt = parse_iso_datetime(date_str)
            weather = item.get("weather", {})
            code = weather.get("code")

            sunrise_ts = item.get("sunrise_ts")
            sunset_ts = item.get("sunset_ts")
            moonrise_ts = item.get("moonrise_ts")
            moonset_ts = item.get("moonset_ts")
            from omni_weather_forecast_apis.utils.time_helpers import datetime_from_unix

            daily.append(
                DailyDataPoint(
                    date=dt.date(),
                    temperature_max=item.get("max_temp"),
                    temperature_min=item.get("min_temp"),
                    apparent_temperature_max=item.get("app_max_temp"),
                    apparent_temperature_min=item.get("app_min_temp"),
                    wind_speed_max=item.get("wind_spd"),
                    wind_gust_max=item.get("wind_gust_spd"),
                    wind_direction_dominant=item.get("wind_dir"),
                    precipitation_sum=item.get("precip"),
                    precipitation_probability_max=(
                        item["pop"] / 100.0 if item.get("pop") is not None else None
                    ),
                    snowfall_sum=item.get("snow"),
                    cloud_cover_mean=item.get("clouds"),
                    uv_index_max=item.get("uv"),
                    visibility_min=item.get("vis"),
                    humidity_mean=item.get("rh"),
                    pressure_sea_mean=item.get("slp"),
                    condition=(
                        WEATHERBIT_CONDITION_MAP.get(code, WeatherCondition.UNKNOWN)
                        if code
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

        raw = data if params.include_raw else None
        return daily, raw

    @staticmethod
    def _check_errors(resp: httpx.Response) -> PluginFetchError | None:
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
        return None


weatherbit_plugin = WeatherbitPlugin()

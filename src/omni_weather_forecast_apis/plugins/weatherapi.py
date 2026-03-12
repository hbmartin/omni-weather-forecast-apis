"""WeatherAPI.com plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.mapping.conditions import WEATHERAPI_CONDITION_MAP
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


class WeatherAPIConfig(BaseModel):
    api_key: str = Field(min_length=1)
    days: int = Field(default=7, ge=1, le=14)
    aqi: bool = Field(default=False)
    alerts: bool = Field(default=True)


class WeatherAPIPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.WEATHERAPI

    @property
    def name(self) -> str:
        return "WeatherAPI"

    def validate_config(self, config: dict[str, Any]) -> WeatherAPIConfig:
        return WeatherAPIConfig(**config)

    async def initialize(self, config: Any) -> WeatherAPIInstance:
        return WeatherAPIInstance(config)


class WeatherAPIInstance:
    def __init__(self, config: WeatherAPIConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.WEATHERAPI

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=False,
            granularity_hourly=True,
            granularity_daily=True,
            max_horizon_hourly_hours=336,
            max_horizon_daily_days=14,
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
            url = "https://api.weatherapi.com/v1/forecast.json"
            query: dict[str, Any] = {
                "key": self._config.api_key,
                "q": f"{params.latitude},{params.longitude}",
                "days": self._config.days,
                "aqi": "yes" if self._config.aqi else "no",
                "alerts": "yes" if self._config.alerts else "no",
            }

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

    def _parse_response(
        self,
        data: dict[str, Any],
        params: PluginFetchParams,
    ) -> PluginFetchResult:
        try:
            forecast_days = data.get("forecast", {}).get("forecastday", [])
            hourly: list[WeatherDataPoint] = []
            daily: list[DailyDataPoint] = []

            for day_data in forecast_days:
                if Granularity.DAILY in params.granularity:
                    daily.append(self._parse_daily_item(day_data))
                if Granularity.HOURLY in params.granularity:
                    hourly.extend(
                        self._parse_hourly_item(hour)
                        for hour in day_data.get("hour", [])
                    )

            source = ModelSource(provider=ProviderId.WEATHERAPI, model="weatherapi")
            forecast = SourceForecast(source=source, hourly=hourly, daily=daily)
            raw = data if params.include_raw else None
            return PluginFetchSuccess(forecasts=[forecast], raw=raw)
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    def _parse_hourly_item(self, item: dict[str, Any]) -> WeatherDataPoint:
        time_str = item.get("time", "")
        dt = parse_iso_datetime(time_str)
        condition = item.get("condition", {})
        code = condition.get("code")

        return WeatherDataPoint(
            timestamp=dt,
            timestamp_unix=item.get("time_epoch", int(dt.timestamp())),
            temperature=item.get("temp_c"),
            apparent_temperature=item.get("feelslike_c"),
            dew_point=item.get("dewpoint_c"),
            humidity=item.get("humidity"),
            wind_speed=(
                item.get("wind_kph", 0) / 3.6
                if item.get("wind_kph") is not None
                else None
            ),
            wind_gust=(
                item.get("gust_kph", 0) / 3.6
                if item.get("gust_kph") is not None
                else None
            ),
            wind_direction=item.get("wind_degree"),
            pressure_sea=item.get("pressure_mb"),
            precipitation=item.get("precip_mm"),
            precipitation_probability=(
                item["chance_of_rain"] / 100.0
                if item.get("chance_of_rain") is not None
                else None
            ),
            snow=(
                item.get("snow_cm", 0) * 10.0
                if item.get("snow_cm") is not None
                else None
            ),
            cloud_cover=item.get("cloud"),
            visibility=item.get("vis_km"),
            uv_index=item.get("uv"),
            condition=(
                WEATHERAPI_CONDITION_MAP.get(code, WeatherCondition.UNKNOWN)
                if code
                else None
            ),
            condition_original=condition.get("text"),
            condition_code_original=code,
            is_day=bool(item.get("is_day")) if item.get("is_day") is not None else None,
        )

    def _parse_daily_item(self, day_data: dict[str, Any]) -> DailyDataPoint:
        date_str = day_data.get("date", "")
        dt = parse_iso_datetime(date_str)
        day = day_data.get("day", {})
        astro = day_data.get("astro", {})
        condition = day.get("condition", {})
        code = condition.get("code")

        return DailyDataPoint(
            date=dt.date(),
            temperature_max=day.get("maxtemp_c"),
            temperature_min=day.get("mintemp_c"),
            wind_speed_max=(
                day["maxwind_kph"] / 3.6 if day.get("maxwind_kph") is not None else None
            ),
            precipitation_sum=day.get("totalprecip_mm"),
            precipitation_probability_max=(
                day["daily_chance_of_rain"] / 100.0
                if day.get("daily_chance_of_rain") is not None
                else None
            ),
            snowfall_sum=(
                day["totalsnow_cm"] * 10.0
                if day.get("totalsnow_cm") is not None
                else None
            ),
            visibility_min=day.get("avgvis_km"),
            humidity_mean=day.get("avghumidity"),
            uv_index_max=day.get("uv"),
            condition=(
                WEATHERAPI_CONDITION_MAP.get(code, WeatherCondition.UNKNOWN)
                if code
                else None
            ),
            summary=condition.get("text"),
            sunrise=self._parse_astro_time(date_str, astro.get("sunrise")),
            sunset=self._parse_astro_time(date_str, astro.get("sunset")),
            moonrise=self._parse_astro_time(date_str, astro.get("moonrise")),
            moonset=self._parse_astro_time(date_str, astro.get("moonset")),
        )

    @staticmethod
    def _parse_astro_time(date_str: str, time_str: str | None) -> Any:
        if not time_str or time_str in {"No moonrise", "No moonset"}:
            return None
        try:
            from datetime import UTC, datetime

            return datetime.strptime(
                f"{date_str} {time_str}",
                "%Y-%m-%d %I:%M %p",
            ).replace(tzinfo=UTC)
        except ValueError:
            return None


weatherapi_plugin = WeatherAPIPlugin()

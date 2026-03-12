"""Weather Unlocked plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.mapping.conditions import map_weather_unlocked_condition
from omni_weather_forecast_apis.mapping.units import ms_from_kmh, safe_convert
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
    WeatherDataPoint,
)
from omni_weather_forecast_apis.utils.time_helpers import parse_iso_datetime


class WeatherUnlockedConfig(BaseModel):
    app_id: str = Field(min_length=1)
    app_key: str = Field(min_length=1)
    lang: str | None = None


class WeatherUnlockedPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.WEATHER_UNLOCKED

    @property
    def name(self) -> str:
        return "Weather Unlocked"

    def validate_config(self, config: dict[str, Any]) -> WeatherUnlockedConfig:
        return WeatherUnlockedConfig(**config)

    async def initialize(self, config: Any) -> WeatherUnlockedInstance:
        return WeatherUnlockedInstance(config)


class WeatherUnlockedInstance:
    def __init__(self, config: WeatherUnlockedConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.WEATHER_UNLOCKED

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=False,
            granularity_hourly=True,
            granularity_daily=True,
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
            location = f"{params.latitude},{params.longitude}"
            url = f"http://api.weatherunlocked.com/api/forecast/{location}"
            query: dict[str, Any] = {
                "app_id": self._config.app_id,
                "app_key": self._config.app_key,
            }
            if self._config.lang:
                query["lang"] = self._config.lang

            resp = await client.get(url, params=query)

            if resp.status_code in (401, 403):
                return PluginFetchError(
                    code=ErrorCode.AUTH_FAILED,
                    message="Invalid credentials",
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
            days = data.get("Days", [])
            hourly: list[WeatherDataPoint] = []
            daily: list[DailyDataPoint] = []

            for day_data in days:
                date_str = day_data.get("date", "")
                if Granularity.DAILY in params.granularity:
                    daily.append(self._parse_daily_item(day_data, date_str))
                if Granularity.HOURLY in params.granularity:
                    hourly.extend(
                        self._parse_timeframe(tf, date_str)
                        for tf in day_data.get("Timeframes", [])
                    )

            source = ModelSource(
                provider=ProviderId.WEATHER_UNLOCKED,
                model="weather_unlocked",
            )
            forecast = SourceForecast(source=source, hourly=hourly, daily=daily)
            raw = data if params.include_raw else None
            return PluginFetchSuccess(forecasts=[forecast], raw=raw)
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    def _parse_timeframe(self, tf: dict[str, Any], date_str: str) -> WeatherDataPoint:
        time_val = tf.get("time", 0)
        hour = int(time_val) // 100
        minute = int(time_val) % 100
        dt = parse_iso_datetime(f"{date_str}T{hour:02d}:{minute:02d}:00")

        wx_code = tf.get("wx_code")

        return WeatherDataPoint(
            timestamp=dt,
            timestamp_unix=int(dt.timestamp()),
            temperature=tf.get("temp_c"),
            apparent_temperature=tf.get("feelslike_c"),
            dew_point=tf.get("dewpoint_c"),
            humidity=tf.get("humid_pct"),
            wind_speed=safe_convert(tf.get("windspd_kmh"), ms_from_kmh),
            wind_gust=safe_convert(tf.get("windgst_kmh"), ms_from_kmh),
            wind_direction=tf.get("winddir_deg"),
            pressure_sea=tf.get("slp_mb"),
            precipitation=tf.get("precip_mm"),
            cloud_cover=tf.get("cloudtotal_pct"),
            visibility=tf.get("vis_km"),
            condition=(
                map_weather_unlocked_condition(wx_code) if wx_code is not None else None
            ),
            condition_original=tf.get("wx_desc"),
            condition_code_original=wx_code,
        )

    def _parse_daily_item(
        self,
        day_data: dict[str, Any],
        date_str: str,
    ) -> DailyDataPoint:
        dt = parse_iso_datetime(date_str)

        return DailyDataPoint(
            date=dt.date(),
            temperature_max=day_data.get("temp_max_c"),
            temperature_min=day_data.get("temp_min_c"),
            wind_speed_max=safe_convert(day_data.get("windspd_max_kmh"), ms_from_kmh),
            wind_gust_max=safe_convert(day_data.get("windgst_max_kmh"), ms_from_kmh),
            precipitation_sum=day_data.get("precip_total_mm"),
            humidity_mean=day_data.get("humid_max_pct"),
            pressure_sea_mean=day_data.get("slp_max_mb"),
        )


weather_unlocked_plugin = WeatherUnlockedPlugin()

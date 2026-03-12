"""Visual Crossing plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.mapping.conditions import VISUAL_CROSSING_ICON_MAP
from omni_weather_forecast_apis.mapping.units import (
    ms_from_kmh,
    safe_convert,
)
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


class VisualCrossingConfig(BaseModel):
    api_key: str = Field(min_length=1)
    include: str = Field(default="hours,days,alerts")


class VisualCrossingPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.VISUAL_CROSSING

    @property
    def name(self) -> str:
        return "Visual Crossing"

    def validate_config(self, config: dict[str, Any]) -> VisualCrossingConfig:
        return VisualCrossingConfig(**config)

    async def initialize(self, config: Any) -> VisualCrossingInstance:
        return VisualCrossingInstance(config)


class VisualCrossingInstance:
    def __init__(self, config: VisualCrossingConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.VISUAL_CROSSING

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=False,
            granularity_hourly=True,
            granularity_daily=True,
            max_horizon_hourly_hours=360,
            max_horizon_daily_days=15,
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
            location = f"{params.latitude},{params.longitude}"
            url = (
                f"https://weather.visualcrossing.com/VisualCrossingWebServices/"
                f"rest/services/timeline/{location}"
            )
            query: dict[str, Any] = {
                "key": self._config.api_key,
                "unitGroup": "metric",
                "include": self._config.include,
                "contentType": "json",
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
            days = data.get("days", [])
            hourly: list[WeatherDataPoint] = []
            daily: list[DailyDataPoint] = []

            for day_data in days:
                date_str = day_data.get("datetime", "")
                if Granularity.DAILY in params.granularity:
                    daily.append(self._parse_daily_item(day_data))
                if Granularity.HOURLY in params.granularity:
                    hourly.extend(
                        self._parse_hourly_item(hour, date_str)
                        for hour in day_data.get("hours", [])
                    )

            source = ModelSource(
                provider=ProviderId.VISUAL_CROSSING,
                model="visual_crossing",
            )
            forecast = SourceForecast(source=source, hourly=hourly, daily=daily)
            raw = data if params.include_raw else None
            return PluginFetchSuccess(forecasts=[forecast], raw=raw)
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    def _parse_hourly_item(
        self,
        item: dict[str, Any],
        date_str: str,
    ) -> WeatherDataPoint:
        time_str = item.get("datetime", "00:00:00")
        dt = parse_iso_datetime(f"{date_str}T{time_str}")
        icon = item.get("icon", "")

        return WeatherDataPoint(
            timestamp=dt,
            timestamp_unix=item.get("datetimeEpoch", int(dt.timestamp())),
            temperature=item.get("temp"),
            apparent_temperature=item.get("feelslike"),
            dew_point=item.get("dew"),
            humidity=item.get("humidity"),
            wind_speed=safe_convert(item.get("windspeed"), ms_from_kmh),
            wind_gust=safe_convert(item.get("windgust"), ms_from_kmh),
            wind_direction=item.get("winddir"),
            pressure_sea=item.get("pressure"),
            precipitation=item.get("precip"),
            precipitation_probability=(
                item["precipprob"] / 100.0
                if item.get("precipprob") is not None
                else None
            ),
            snow=item.get("snow"),
            snow_depth=item.get("snowdepth"),
            cloud_cover=item.get("cloudcover"),
            visibility=item.get("visibility"),
            uv_index=item.get("uvindex"),
            solar_radiation_ghi=item.get("solarradiation"),
            condition=(
                VISUAL_CROSSING_ICON_MAP.get(icon, WeatherCondition.UNKNOWN)
                if icon
                else None
            ),
            condition_original=item.get("conditions"),
            condition_code_original=icon,
        )

    def _parse_daily_item(self, day_data: dict[str, Any]) -> DailyDataPoint:
        date_str = day_data.get("datetime", "")
        dt = parse_iso_datetime(date_str)
        icon = day_data.get("icon", "")

        sunrise_epoch = day_data.get("sunriseEpoch")
        sunset_epoch = day_data.get("sunsetEpoch")
        from omni_weather_forecast_apis.utils.time_helpers import datetime_from_unix

        return DailyDataPoint(
            date=dt.date(),
            temperature_max=day_data.get("tempmax"),
            temperature_min=day_data.get("tempmin"),
            apparent_temperature_max=day_data.get("feelslikemax"),
            apparent_temperature_min=day_data.get("feelslikemin"),
            wind_speed_max=safe_convert(day_data.get("windspeed"), ms_from_kmh),
            wind_gust_max=safe_convert(day_data.get("windgust"), ms_from_kmh),
            wind_direction_dominant=day_data.get("winddir"),
            precipitation_sum=day_data.get("precip"),
            precipitation_probability_max=(
                day_data["precipprob"] / 100.0
                if day_data.get("precipprob") is not None
                else None
            ),
            snowfall_sum=day_data.get("snow"),
            cloud_cover_mean=day_data.get("cloudcover"),
            uv_index_max=day_data.get("uvindex"),
            visibility_min=day_data.get("visibility"),
            humidity_mean=day_data.get("humidity"),
            pressure_sea_mean=day_data.get("pressure"),
            condition=(
                VISUAL_CROSSING_ICON_MAP.get(icon, WeatherCondition.UNKNOWN)
                if icon
                else None
            ),
            summary=day_data.get("description"),
            sunrise=datetime_from_unix(sunrise_epoch) if sunrise_epoch else None,
            sunset=datetime_from_unix(sunset_epoch) if sunset_epoch else None,
            solar_radiation_sum=day_data.get("solarenergy"),
        )


visual_crossing_plugin = VisualCrossingPlugin()

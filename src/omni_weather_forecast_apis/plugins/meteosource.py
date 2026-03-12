"""Meteosource plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.mapping.conditions import map_meteosource_condition
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


class MeteosourceConfig(BaseModel):
    api_key: str = Field(min_length=1)
    sections: list[str] = Field(
        default=["current", "hourly", "daily"],
    )


class MeteosourcePlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.METEOSOURCE

    @property
    def name(self) -> str:
        return "Meteosource"

    def validate_config(self, config: dict[str, Any]) -> MeteosourceConfig:
        return MeteosourceConfig(**config)

    async def initialize(self, config: Any) -> MeteosourceInstance:
        return MeteosourceInstance(config)


class MeteosourceInstance:
    def __init__(self, config: MeteosourceConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.METEOSOURCE

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=True,
            granularity_hourly=True,
            granularity_daily=True,
            max_horizon_minutely_hours=1,
            max_horizon_hourly_hours=168,
            max_horizon_daily_days=30,
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
            url = "https://www.meteosource.com/api/v1/free/point"
            sections = list(self._config.sections)
            if Granularity.HOURLY in params.granularity and "hourly" not in sections:
                sections.append("hourly")
            if Granularity.DAILY in params.granularity and "daily" not in sections:
                sections.append("daily")

            query: dict[str, Any] = {
                "key": self._config.api_key,
                "lat": params.latitude,
                "lon": params.longitude,
                "sections": ",".join(sections),
                "units": "metric",
                "timezone": "UTC",
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
            hourly = self._parse_hourly(data.get("hourly", {}).get("data", []))
            daily = self._parse_daily(data.get("daily", {}).get("data", []))

            source = ModelSource(provider=ProviderId.METEOSOURCE, model="meteosource")
            forecast = SourceForecast(source=source, hourly=hourly, daily=daily)
            raw = data if params.include_raw else None
            return PluginFetchSuccess(forecasts=[forecast], raw=raw)
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    def _parse_hourly(self, items: list[dict[str, Any]]) -> list[WeatherDataPoint]:
        result: list[WeatherDataPoint] = []
        for item in items:
            date_str = item.get("date", "")
            dt = parse_iso_datetime(date_str)
            icon_id = item.get("icon")

            wind = item.get("wind", {})
            precip = item.get("precipitation", {})
            cloud = item.get("cloud_cover", {})

            result.append(
                WeatherDataPoint(
                    timestamp=dt,
                    timestamp_unix=int(dt.timestamp()),
                    temperature=item.get("temperature"),
                    apparent_temperature=item.get("feels_like"),
                    dew_point=item.get("dew_point"),
                    humidity=item.get("humidity"),
                    wind_speed=wind.get("speed"),
                    wind_gust=wind.get("gusts"),
                    wind_direction=wind.get("dir"),
                    pressure_sea=item.get("pressure"),
                    precipitation=precip.get("total"),
                    cloud_cover=(
                        cloud.get("total") if isinstance(cloud, dict) else cloud
                    ),
                    visibility=item.get("visibility"),
                    uv_index=item.get("uv_index"),
                    condition=(
                        map_meteosource_condition(icon_id)
                        if icon_id is not None
                        else None
                    ),
                    condition_code_original=icon_id,
                    condition_original=item.get("summary"),
                ),
            )
        return result

    def _parse_daily(self, items: list[dict[str, Any]]) -> list[DailyDataPoint]:
        result: list[DailyDataPoint] = []
        for item in items:
            date_str = item.get("day", "")
            dt = parse_iso_datetime(date_str)
            icon_id = item.get("icon")

            all_day = item.get("all_day", {})
            wind = all_day.get("wind", {})
            precip = all_day.get("precipitation", {})
            cloud = all_day.get("cloud_cover", {})

            result.append(
                DailyDataPoint(
                    date=dt.date(),
                    temperature_max=all_day.get("temperature_max"),
                    temperature_min=all_day.get("temperature_min"),
                    wind_speed_max=wind.get("speed"),
                    wind_gust_max=wind.get("gusts"),
                    wind_direction_dominant=wind.get("dir"),
                    precipitation_sum=precip.get("total"),
                    cloud_cover_mean=(
                        cloud.get("total") if isinstance(cloud, dict) else cloud
                    ),
                    visibility_min=all_day.get("visibility"),
                    uv_index_max=all_day.get("uv_index"),
                    humidity_mean=all_day.get("humidity"),
                    pressure_sea_mean=all_day.get("pressure"),
                    condition=(
                        map_meteosource_condition(icon_id)
                        if icon_id is not None
                        else None
                    ),
                    summary=item.get("summary"),
                ),
            )
        return result


meteosource_plugin = MeteosourcePlugin()

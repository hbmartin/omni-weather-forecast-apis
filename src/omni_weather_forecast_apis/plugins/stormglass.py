"""Stormglass plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.types.plugin import (
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
)
from omni_weather_forecast_apis.types.schema import (
    ErrorCode,
    ModelSource,
    ProviderId,
    SourceForecast,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.utils.time_helpers import parse_iso_datetime


class StormglassConfig(BaseModel):
    api_key: str = Field(min_length=1)
    sources: list[str] = Field(default=["sg"])
    params: list[str] = Field(
        default=[
            "airTemperature",
            "humidity",
            "pressure",
            "windSpeed",
            "windDirection",
            "windGust",
            "cloudCover",
            "precipitation",
            "visibility",
        ],
    )


class StormglassPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.STORMGLASS

    @property
    def name(self) -> str:
        return "Stormglass"

    def validate_config(self, config: dict[str, Any]) -> StormglassConfig:
        return StormglassConfig(**config)

    async def initialize(self, config: Any) -> StormglassInstance:
        return StormglassInstance(config)


class StormglassInstance:
    def __init__(self, config: StormglassConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.STORMGLASS

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=False,
            granularity_hourly=True,
            granularity_daily=False,
            requires_api_key=True,
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
            url = "https://api.stormglass.io/v2/weather/point"
            query: dict[str, Any] = {
                "lat": params.latitude,
                "lng": params.longitude,
                "params": ",".join(self._config.params),
                "source": ",".join(self._config.sources),
            }
            headers = {"Authorization": self._config.api_key}

            resp = await client.get(url, params=query, headers=headers)

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
            hours = data.get("hours", [])
            forecasts: list[SourceForecast] = []

            for source_name in self._config.sources:
                hourly = self._parse_hourly_for_source(hours, source_name)
                source = ModelSource(provider=ProviderId.STORMGLASS, model=source_name)
                forecasts.append(SourceForecast(source=source, hourly=hourly))

            raw = data if params.include_raw else None
            return PluginFetchSuccess(forecasts=forecasts, raw=raw)
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    @staticmethod
    def _source_val(
        hour: dict[str, Any],
        param: str,
        source_name: str,
    ) -> float | None:
        """Extract a value for a specific source from a stormglass data point."""
        val = hour.get(param, {})
        return val.get(source_name) if isinstance(val, dict) else None

    def _parse_hourly_for_source(
        self,
        hours: list[dict[str, Any]],
        source_name: str,
    ) -> list[WeatherDataPoint]:
        result: list[WeatherDataPoint] = []
        sv = self._source_val

        for hour in hours:
            time_str = hour.get("time", "")
            dt = parse_iso_datetime(time_str)

            result.append(
                WeatherDataPoint(
                    timestamp=dt,
                    timestamp_unix=int(dt.timestamp()),
                    temperature=sv(hour, "airTemperature", source_name),
                    humidity=sv(hour, "humidity", source_name),
                    wind_speed=sv(hour, "windSpeed", source_name),
                    wind_gust=sv(hour, "windGust", source_name),
                    wind_direction=sv(hour, "windDirection", source_name),
                    pressure_sea=sv(hour, "pressure", source_name),
                    precipitation=sv(hour, "precipitation", source_name),
                    cloud_cover=sv(hour, "cloudCover", source_name),
                    visibility=sv(hour, "visibility", source_name),
                ),
            )
        return result


stormglass_plugin = StormglassPlugin()

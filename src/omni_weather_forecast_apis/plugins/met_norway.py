"""MET Norway (Yr) plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.mapping.conditions import map_met_norway_condition
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


class METNorwayConfig(BaseModel):
    user_agent: str = Field(min_length=1)
    altitude: int | None = Field(None)
    variant: str = "complete"


class METNorwayPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.MET_NORWAY

    @property
    def name(self) -> str:
        return "MET Norway"

    def validate_config(self, config: dict[str, Any]) -> METNorwayConfig:
        return METNorwayConfig(**config)

    async def initialize(self, config: Any) -> METNorwayInstance:
        return METNorwayInstance(config)


class METNorwayInstance:
    def __init__(self, config: METNorwayConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.MET_NORWAY

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=False,
            granularity_hourly=True,
            granularity_daily=False,
            max_horizon_hourly_hours=216,
            requires_api_key=False,
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
            url = (
                "https://api.met.no/weatherapi/locationforecast/2.0/"
                f"{self._config.variant}"
            )
            query: dict[str, Any] = {
                "lat": round(params.latitude, 4),
                "lon": round(params.longitude, 4),
            }
            if self._config.altitude is not None:
                query["altitude"] = self._config.altitude

            headers = {"User-Agent": self._config.user_agent}

            resp = await client.get(url, params=query, headers=headers)

            if resp.status_code == 403:
                return PluginFetchError(
                    code=ErrorCode.AUTH_FAILED,
                    message="Forbidden (check User-Agent header)",
                    http_status=403,
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
            timeseries = data.get("properties", {}).get("timeseries", [])
            hourly: list[WeatherDataPoint] = []

            for entry in timeseries:
                time_str = entry.get("time", "")
                dt = parse_iso_datetime(time_str)
                details = entry.get("data", {}).get("instant", {}).get("details", {})

                next_1h = entry.get("data", {}).get("next_1_hours", {})
                summary_code = next_1h.get("summary", {}).get("symbol_code", "")
                next_1h_details = next_1h.get("details", {})

                condition = (
                    map_met_norway_condition(summary_code) if summary_code else None
                )

                hourly.append(
                    WeatherDataPoint(
                        timestamp=dt,
                        timestamp_unix=int(dt.timestamp()),
                        temperature=details.get("air_temperature"),
                        dew_point=details.get("dew_point_temperature"),
                        humidity=details.get("relative_humidity"),
                        wind_speed=details.get("wind_speed"),
                        wind_gust=details.get("wind_speed_of_gust"),
                        wind_direction=details.get("wind_from_direction"),
                        pressure_sea=details.get("air_pressure_at_sea_level"),
                        cloud_cover=details.get("cloud_area_fraction"),
                        cloud_cover_low=details.get("cloud_area_fraction_low"),
                        cloud_cover_mid=details.get("cloud_area_fraction_medium"),
                        cloud_cover_high=details.get("cloud_area_fraction_high"),
                        uv_index=details.get("ultraviolet_index_clear_sky"),
                        precipitation=next_1h_details.get("precipitation_amount"),
                        condition=condition,
                        condition_original=summary_code or None,
                        condition_code_original=summary_code or None,
                    ),
                )

            source = ModelSource(provider=ProviderId.MET_NORWAY, model="met_norway")
            forecast = SourceForecast(source=source, hourly=hourly)
            raw = data if params.include_raw else None
            return PluginFetchSuccess(forecasts=[forecast], raw=raw)
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))


met_norway_plugin = METNorwayPlugin()

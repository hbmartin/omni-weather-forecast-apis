"""NWS (National Weather Service) plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.mapping.conditions import map_nws_condition
from omni_weather_forecast_apis.mapping.units import (
    celsius_from_fahrenheit,
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
    ErrorCode,
    ModelSource,
    ProviderId,
    SourceForecast,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.utils.time_helpers import parse_iso_datetime


class NWSGridOverride(BaseModel):
    office: str
    grid_x: int
    grid_y: int


class NWSConfig(BaseModel):
    user_agent: str = Field(min_length=1)
    grid_override: NWSGridOverride | None = None


class NWSPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.NWS

    @property
    def name(self) -> str:
        return "NWS"

    def validate_config(self, config: dict[str, Any]) -> NWSConfig:
        return NWSConfig(**config)

    async def initialize(self, config: Any) -> NWSInstance:
        return NWSInstance(config)


class NWSInstance:
    def __init__(self, config: NWSConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.NWS

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=False,
            granularity_hourly=True,
            granularity_daily=True,
            max_horizon_hourly_hours=156,
            max_horizon_daily_days=7,
            requires_api_key=False,
            multi_model=False,
            coverage="us_only",
            alerts=True,
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        try:
            headers = {"User-Agent": self._config.user_agent}

            if self._config.grid_override:
                grid = self._config.grid_override
                forecast_url = (
                    f"https://api.weather.gov/gridpoints/"
                    f"{grid.office}/{grid.grid_x},{grid.grid_y}/forecast/hourly"
                )
            else:
                points_resp = await client.get(
                    f"https://api.weather.gov/points/{params.latitude},{params.longitude}",
                    headers=headers,
                )
                if points_resp.status_code != 200:
                    return PluginFetchError(
                        code=ErrorCode.NOT_AVAILABLE,
                        message=f"Points lookup failed: HTTP {points_resp.status_code}",
                        http_status=points_resp.status_code,
                    )
                points_data = points_resp.json()
                forecast_url = points_data["properties"]["forecastHourly"]

            resp = await client.get(forecast_url, headers=headers)

            if resp.status_code == 403:
                return PluginFetchError(
                    code=ErrorCode.AUTH_FAILED,
                    message="Forbidden (check User-Agent)",
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
            periods = data.get("properties", {}).get("periods", [])
            hourly: list[WeatherDataPoint] = []

            for period in periods:
                start_time = period.get("startTime", "")
                dt = parse_iso_datetime(start_time)

                temp_val = period.get("temperature")
                temp_unit = period.get("temperatureUnit", "F")
                temperature = (
                    safe_convert(float(temp_val), celsius_from_fahrenheit)
                    if temp_unit == "F" and temp_val is not None
                    else (float(temp_val) if temp_val is not None else None)
                )

                wind_speed_str = period.get("windSpeed", "")
                wind_speed = self._parse_wind_speed(wind_speed_str)

                wind_dir_str = period.get("windDirection", "")
                wind_direction = self._compass_to_degrees(wind_dir_str)

                icon_url = period.get("icon", "")
                condition = map_nws_condition(icon_url) if icon_url else None

                humidity_val = period.get("relativeHumidity", {})
                humidity = (
                    humidity_val.get("value")
                    if isinstance(humidity_val, dict)
                    else None
                )

                hourly.append(
                    WeatherDataPoint(
                        timestamp=dt,
                        timestamp_unix=int(dt.timestamp()),
                        temperature=temperature,
                        humidity=humidity,
                        wind_speed=wind_speed,
                        wind_direction=wind_direction,
                        condition=condition,
                        condition_original=period.get("shortForecast"),
                        is_day=period.get("isDaytime"),
                    ),
                )

            source = ModelSource(provider=ProviderId.NWS, model="nws")
            forecast = SourceForecast(source=source, hourly=hourly)
            raw = data if params.include_raw else None
            return PluginFetchSuccess(forecasts=[forecast], raw=raw)
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    @staticmethod
    def _parse_wind_speed(wind_str: str) -> float | None:
        """Parse NWS wind speed string like '10 mph' or '5 to 10 mph'."""
        if not wind_str:
            return None
        import re

        numbers = re.findall(r"\d+", wind_str)
        if not numbers:
            return None
        mph = float(numbers[-1])
        return mph * 0.44704

    @staticmethod
    def _compass_to_degrees(direction: str) -> float | None:
        """Convert compass direction to degrees."""
        compass_map: dict[str, float] = {
            "N": 0,
            "NNE": 22.5,
            "NE": 45,
            "ENE": 67.5,
            "E": 90,
            "ESE": 112.5,
            "SE": 135,
            "SSE": 157.5,
            "S": 180,
            "SSW": 202.5,
            "SW": 225,
            "WSW": 247.5,
            "W": 270,
            "WNW": 292.5,
            "NW": 315,
            "NNW": 337.5,
        }
        return compass_map.get(direction)


nws_plugin = NWSPlugin()

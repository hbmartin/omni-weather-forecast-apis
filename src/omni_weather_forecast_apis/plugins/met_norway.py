"""MET Norway provider adapter."""

from __future__ import annotations

from typing import Any, Final

import httpx

from omni_weather_forecast_apis.mapping import map_met_norway_condition
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_hourly_point,
    build_source_forecast,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    METNorwayConfig,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
)

MET_NORWAY_BASE_URL: Final = "https://api.met.no/weatherapi/locationforecast/2.0"


def _summary_block(entry: dict[str, Any]) -> dict[str, Any] | None:
    data = entry.get("data")
    if not isinstance(data, dict):
        return None
    candidate = data.get("next_1_hours")
    return candidate if isinstance(candidate, dict) else None


def _symbol_to_day_flag(symbol_code: str | None) -> bool | None:
    if symbol_code is None:
        return None
    if symbol_code.endswith("_day"):
        return True
    if symbol_code.endswith("_night"):
        return False
    return None


class METNorwayInstance(BasePluginInstance[METNorwayConfig]):
    """Configured MET Norway provider."""

    def __init__(self, config: METNorwayConfig) -> None:
        super().__init__(
            provider_id=ProviderId.MET_NORWAY,
            config=config,
            capabilities=PluginCapabilities(
                granularity_minutely=False,
                granularity_hourly=True,
                granularity_daily=False,
                max_horizon_hourly_hours=9 * 24,
                max_horizon_daily_days=None,
                requires_api_key=False,
                multi_model=False,
                coverage="nordic",
            ),
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        payload, error = await self._get_json(
            client,
            f"{MET_NORWAY_BASE_URL}/{self.config.variant}",
            params=self._request_params(params),
            headers={"User-Agent": self.config.user_agent},
        )
        if error is not None:
            return error
        if payload is None or not isinstance(payload, dict):
            return self._error(
                ErrorCode.PARSE,
                "MET Norway returned an invalid payload",
            )

        try:
            forecasts = [
                build_source_forecast(
                    ProviderId.MET_NORWAY,
                    hourly=self._parse_hourly(payload),
                ),
            ]
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse MET Norway payload: {exc}",
            )
        return self._success(forecasts, raw=payload if params.include_raw else None)

    def _request_params(self, params: PluginFetchParams) -> dict[str, float | int]:
        request_params: dict[str, float | int] = {
            "lat": round(params.latitude, 4),
            "lon": round(params.longitude, 4),
        }
        if self.config.altitude is not None:
            request_params["altitude"] = self.config.altitude
        return request_params

    def _parse_hourly(self, payload: dict[str, Any]) -> list[Any]:
        properties = payload.get("properties")
        if not isinstance(properties, dict):
            return []
        timeseries = properties.get("timeseries")
        if not isinstance(timeseries, list):
            return []

        points: list[Any] = []
        for entry in timeseries:
            if not isinstance(entry, dict):
                continue
            data = entry.get("data")
            if not isinstance(data, dict):
                continue
            instant = data.get("instant")
            if not isinstance(instant, dict):
                continue
            details = instant.get("details")
            if not isinstance(details, dict):
                continue

            summary = _summary_block(entry)
            summary_details = (
                summary.get("details") if isinstance(summary, dict) else None
            )
            summary_block = (
                summary.get("summary") if isinstance(summary, dict) else None
            )
            symbol_code = (
                summary_block.get("symbol_code")
                if isinstance(summary_block, dict)
                and isinstance(summary_block.get("symbol_code"), str)
                else None
            )

            points.append(
                build_hourly_point(
                    entry["time"],
                    temperature=as_float(details.get("air_temperature")),
                    dew_point=as_float(details.get("dew_point_temperature")),
                    humidity=as_float(details.get("relative_humidity")),
                    wind_speed=as_float(details.get("wind_speed")),
                    wind_gust=as_float(details.get("wind_speed_of_gust")),
                    wind_direction=as_float(details.get("wind_from_direction")),
                    pressure_sea=as_float(details.get("air_pressure_at_sea_level")),
                    pressure_surface=as_float(details.get("surface_air_pressure")),
                    precipitation=(
                        as_float(summary_details.get("precipitation_amount"))
                        if isinstance(summary_details, dict)
                        else None
                    ),
                    cloud_cover=as_float(details.get("cloud_area_fraction")),
                    cloud_cover_low=as_float(details.get("cloud_area_fraction_low")),
                    cloud_cover_mid=as_float(details.get("cloud_area_fraction_medium")),
                    cloud_cover_high=as_float(details.get("cloud_area_fraction_high")),
                    uv_index=as_float(details.get("ultraviolet_index_clear_sky")),
                    condition=(
                        map_met_norway_condition(symbol_code)
                        if symbol_code is not None
                        else None
                    ),
                    condition_original=symbol_code,
                    condition_code_original=symbol_code,
                    is_day=_symbol_to_day_flag(symbol_code),
                ),
            )
        return points


class METNorwayPlugin(BasePlugin[METNorwayConfig]):
    """MET Norway plugin facade."""

    config_model = METNorwayConfig
    instance_cls = METNorwayInstance
    _id = ProviderId.MET_NORWAY
    _name = "MET Norway"


met_norway_plugin = METNorwayPlugin()

"""Stormglass provider adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import httpx

from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_hourly_point,
    build_source_forecast,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    StormglassConfig,
)

STORMGLASS_URL: Final = "https://api.stormglass.io/v2/weather/point"


def _value_for_source(value: Any, source: str) -> float | None:
    if isinstance(value, Mapping):
        return as_float(value.get(source))
    return as_float(value)


class StormglassInstance(BasePluginInstance[StormglassConfig]):
    """Configured Stormglass provider."""

    def __init__(self, config: StormglassConfig) -> None:
        super().__init__(
            provider_id=ProviderId.STORMGLASS,
            config=config,
            capabilities=PluginCapabilities(
                granularity_minutely=False,
                granularity_hourly=True,
                granularity_daily=False,
                max_horizon_hourly_hours=None,
                requires_api_key=True,
                multi_model=True,
                coverage="global",
            ),
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        payload, error = await self._get_json(
            client,
            STORMGLASS_URL,
            params={
                "lat": params.latitude,
                "lng": params.longitude,
                "params": ",".join(self.config.params),
                "source": ",".join(self.config.sources),
            },
            headers={"Authorization": self.config.api_key},
        )
        if error is not None:
            return error
        if payload is None or not isinstance(payload, dict):
            return self._error(
                ErrorCode.PARSE,
                "Stormglass returned an invalid payload",
            )

        try:
            forecasts = self._parse_payload(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse Stormglass payload: {exc}",
            )
        return self._success(forecasts, raw=payload if params.include_raw else None)

    def _parse_payload(self, payload: dict[str, Any]) -> list[Any]:
        hours = payload.get("hours")
        if not isinstance(hours, list):
            return []

        forecasts: list[Any] = []
        for source in self.config.sources:
            forecasts.append(
                build_source_forecast(
                    ProviderId.STORMGLASS,
                    model=source,
                    hourly=self._parse_hourly(hours, source),
                ),
            )
        return forecasts

    def _parse_hourly(self, hours: list[Any], source: str) -> list[Any]:
        points: list[Any] = []
        for row in hours:
            if not isinstance(row, dict):
                continue
            points.append(
                build_hourly_point(
                    row["time"],
                    temperature=_value_for_source(row.get("airTemperature"), source),
                    humidity=_value_for_source(row.get("humidity"), source),
                    wind_speed=_value_for_source(row.get("windSpeed"), source),
                    wind_gust=_value_for_source(row.get("windGust"), source),
                    wind_direction=_value_for_source(row.get("windDirection"), source),
                    pressure_sea=_value_for_source(row.get("pressure"), source),
                    precipitation=_value_for_source(row.get("precipitation"), source),
                    cloud_cover=_value_for_source(row.get("cloudCover"), source),
                    visibility=_value_for_source(row.get("visibility"), source),
                ),
            )
        return points


class StormglassPlugin(BasePlugin[StormglassConfig]):
    """Stormglass plugin facade."""

    config_model = StormglassConfig
    instance_cls = StormglassInstance
    _id = ProviderId.STORMGLASS
    _name = "Stormglass"


stormglass_plugin = StormglassPlugin()

"""Google Weather placeholder adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from omni_weather_forecast_apis.plugins._base import BasePlugin, BasePluginInstance
from omni_weather_forecast_apis.types import (
    ErrorCode,
    GoogleWeatherConfig,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
)

if TYPE_CHECKING:
    import httpx

_CAPABILITIES = PluginCapabilities(
    granularity_minutely=False,
    granularity_hourly=False,
    granularity_daily=False,
)


class _GoogleWeatherInstance(BasePluginInstance[GoogleWeatherConfig]):
    """Configured Google Weather adapter."""

    def __init__(self, config: GoogleWeatherConfig) -> None:
        super().__init__(ProviderId.GOOGLE_WEATHER, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        """Return a structured unavailable response."""

        _ = (params, client)
        return self._error(
            ErrorCode.NOT_AVAILABLE,
            "Google Weather integration details are not publicly specified enough "
            "for a stable adapter.",
        )


class _GoogleWeatherPlugin(BasePlugin[GoogleWeatherConfig]):
    """Google Weather plugin facade."""

    config_model = GoogleWeatherConfig
    instance_cls = _GoogleWeatherInstance
    _id = ProviderId.GOOGLE_WEATHER
    _name = "Google Weather"


google_weather_plugin = _GoogleWeatherPlugin()

__all__ = ["google_weather_plugin"]

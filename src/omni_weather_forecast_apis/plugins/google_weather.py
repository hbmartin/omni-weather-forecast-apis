"""Google Weather plugin (placeholder — API details are limited)."""

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from omni_weather_forecast_apis.types.plugin import (
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
)
from omni_weather_forecast_apis.types.schema import (
    ErrorCode,
    ProviderId,
)

if TYPE_CHECKING:
    import httpx


class GoogleWeatherConfig(BaseModel):
    api_key: str = Field(min_length=1)


class GoogleWeatherPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.GOOGLE_WEATHER

    @property
    def name(self) -> str:
        return "Google Weather"

    def validate_config(self, config: dict[str, Any]) -> GoogleWeatherConfig:
        return GoogleWeatherConfig(**config)

    async def initialize(self, config: Any) -> GoogleWeatherInstance:
        return GoogleWeatherInstance(config)


class GoogleWeatherInstance:
    def __init__(self, config: GoogleWeatherConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.GOOGLE_WEATHER

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
        return PluginFetchError(
            code=ErrorCode.NOT_AVAILABLE,
            message="Google Weather API is not yet publicly available",
        )


google_weather_plugin = GoogleWeatherPlugin()

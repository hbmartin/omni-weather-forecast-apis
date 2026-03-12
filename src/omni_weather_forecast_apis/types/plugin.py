"""Plugin interface types."""

from typing import Any, Literal, Protocol, runtime_checkable

import httpx  # noqa: TC002
from pydantic import BaseModel

from omni_weather_forecast_apis.types.schema import (  # noqa: TC001
    ErrorCode,
    Granularity,
    ProviderId,
    SourceForecast,
)


class PluginCapabilities(BaseModel):
    """Describes what a provider supports."""

    granularity_minutely: bool = False
    granularity_hourly: bool = True
    granularity_daily: bool = True

    max_horizon_minutely_hours: float | None = None
    max_horizon_hourly_hours: float | None = None
    max_horizon_daily_days: float | None = None

    requires_api_key: bool = True
    multi_model: bool = False
    coverage: str = "global"
    alerts: bool = False


class PluginFetchParams(BaseModel):
    latitude: float
    longitude: float
    granularity: list[Granularity]
    include_raw: bool = False


class PluginFetchSuccess(BaseModel):
    status: Literal["success"] = "success"
    forecasts: list[SourceForecast]
    raw: Any | None = None


class PluginFetchError(BaseModel):
    status: Literal["error"] = "error"
    code: ErrorCode
    message: str
    http_status: int | None = None
    raw: Any | None = None


PluginFetchResult = PluginFetchSuccess | PluginFetchError


@runtime_checkable
class WeatherPlugin(Protocol):
    """Protocol that every provider plugin must implement."""

    @property
    def id(self) -> ProviderId: ...

    @property
    def name(self) -> str: ...

    def validate_config(self, config: dict[str, Any]) -> Any: ...

    async def initialize(self, config: Any) -> PluginInstance: ...


@runtime_checkable
class PluginInstance(Protocol):
    """A configured, ready-to-use provider instance."""

    @property
    def provider_id(self) -> ProviderId: ...

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult: ...

    def get_capabilities(self) -> PluginCapabilities: ...

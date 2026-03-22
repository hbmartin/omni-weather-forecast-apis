from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, ConfigDict

from omni_weather_forecast_apis.types.schema import (
    ErrorCode,
    Granularity,
    ProviderId,
    SourceForecast,
)


class ProviderConfigModel(BaseModel):
    """Base model for provider-specific config payloads."""

    model_config = ConfigDict(extra="forbid")


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
    """Request parameters passed to one provider."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    latitude: float
    longitude: float
    granularity: list[Granularity]
    language: str = "en"
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
    def id(self) -> ProviderId:
        """Unique provider identifier."""

    @property
    def name(self) -> str:
        """Human-readable provider name."""

    def validate_config(self, config: dict[str, Any]) -> Any:
        """Return a validated config object or raise ValidationError."""

    async def initialize(self, config: Any) -> PluginInstance:
        """Return a configured plugin instance."""


@runtime_checkable
class PluginInstance(Protocol):
    """A configured, ready-to-use provider instance."""

    @property
    def provider_id(self) -> ProviderId:
        """Return the provider identifier."""

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        """
        Fetch and normalize forecast data.

        Implementations must not raise. Errors should be reported through
        PluginFetchError instead.
        """

    def get_capabilities(self) -> PluginCapabilities:
        """Return provider capabilities metadata."""



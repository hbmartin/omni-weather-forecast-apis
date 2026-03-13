from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, ConfigDict, Field

from omni_weather_forecast_apis.types.schema import (
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


class OpenWeatherConfig(BaseModel):
    api_key: str = Field(min_length=1)
    exclude: list[str] | None = Field(
        None,
        description="Blocks to exclude: current, minutely, hourly, daily, alerts",
    )
    units: Literal["standard", "metric", "imperial"] = "metric"


class OpenMeteoConfig(BaseModel):
    api_key: str | None = None
    models: list[str] = Field(default_factory=lambda: ["best_match"])
    extra_hourly_vars: list[str] | None = None
    extra_daily_vars: list[str] | None = None


class NWSGridOverride(BaseModel):
    office: str
    grid_x: int
    grid_y: int


class NWSConfig(BaseModel):
    user_agent: str = Field(min_length=1)
    grid_override: NWSGridOverride | None = None


class WeatherAPIConfig(BaseModel):
    api_key: str = Field(min_length=1)
    days: int = Field(default=7, ge=1, le=14)
    aqi: bool = False
    alerts: bool = True


class TomorrowIOConfig(BaseModel):
    api_key: str = Field(min_length=1)
    fields: list[str] | None = None


class VisualCrossingConfig(BaseModel):
    api_key: str = Field(min_length=1)
    include: str = "hours,days,alerts"


class WeatherbitConfig(BaseModel):
    api_key: str = Field(min_length=1)
    hours: int = Field(default=48, ge=1, le=240)
    units: Literal["M", "S", "I"] = "M"


class MeteosourceConfig(BaseModel):
    api_key: str = Field(min_length=1)
    sections: list[str] = Field(
        default_factory=lambda: ["current", "hourly", "daily"],
    )


class PirateWeatherConfig(BaseModel):
    api_key: str = Field(min_length=1)
    extend_hourly: bool = False
    version: Literal["1", "2"] = "2"


class METNorwayConfig(BaseModel):
    user_agent: str = Field(min_length=1)
    altitude: int | None = None
    variant: Literal["compact", "complete"] = "complete"


class GoogleWeatherConfig(BaseModel):
    api_key: str = Field(min_length=1)


class StormglassConfig(BaseModel):
    api_key: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=lambda: ["sg"])
    params: list[str] = Field(
        default_factory=lambda: [
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


class WeatherUnlockedConfig(BaseModel):
    app_id: str = Field(min_length=1)
    app_key: str = Field(min_length=1)
    lang: str | None = None

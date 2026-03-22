from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from omni_weather_forecast_apis.types.schema import Granularity, ProviderId


class ProviderRegistration(BaseModel):
    """Configuration for one registered provider."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    plugin_id: ProviderId
    config: dict[str, Any]
    rate_limit_rps: float | None = Field(default=None, gt=0)
    timeout_ms: float | None = Field(default=None, gt=0)
    enabled: bool = True


class RateLimitConfig(BaseModel):
    """Global rate-limiting policy."""

    max_in_flight: int = Field(
        default=10,
        ge=1,
        validation_alias=AliasChoices("max_in_flight", "max_concurrent"),
    )
    max_requests_per_second: float = Field(default=20, gt=0)


class OmniWeatherConfig(BaseModel):
    """Top-level client configuration."""

    providers: list[ProviderRegistration]
    rate_limiting: RateLimitConfig = Field(default_factory=RateLimitConfig)
    default_timeout_ms: float = Field(default=10_000, gt=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    sqlite: str | None = None
    granularity: list[Granularity] = Field(
        default=[Granularity.MINUTELY, Granularity.HOURLY, Granularity.DAILY],
    )
    language: str = "en"
    include_raw: bool = False
    debug: bool = False

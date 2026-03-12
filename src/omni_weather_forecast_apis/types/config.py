"""Configuration types for the OmniWeather client."""

from typing import Any

from pydantic import BaseModel, Field

from omni_weather_forecast_apis.types.schema import ProviderId  # noqa: TC001


class ProviderRegistration(BaseModel):
    """Configuration for a single provider within the client."""

    plugin_id: ProviderId = Field(description="Which plugin to use")
    config: dict[str, Any] = Field(
        description="Plugin-specific config (validated at init)",
    )
    rate_limit_rps: float | None = Field(
        None,
        description="Per-provider max requests/sec override",
    )
    timeout_ms: float | None = Field(
        None,
        description="Per-provider timeout override in ms",
    )
    enabled: bool = True


class RateLimitConfig(BaseModel):
    max_concurrent: int = Field(
        default=10,
        description="Max concurrent outgoing HTTP requests across all providers",
    )
    max_requests_per_second: float = Field(
        default=20,
        description="Global requests per second ceiling",
    )


class OmniWeatherConfig(BaseModel):
    providers: list[ProviderRegistration]
    rate_limiting: RateLimitConfig = Field(default_factory=RateLimitConfig)
    default_timeout_ms: float = Field(default=10_000)

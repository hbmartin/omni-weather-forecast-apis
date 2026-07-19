from __future__ import annotations

from typing import Any, Self

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from omni_weather_forecast_apis.types.schema import Granularity, ProviderId


class RetryPolicy(BaseModel):
    """Retry policy for transient provider failures."""

    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_backoff_ms: float = Field(default=500, gt=0)
    max_backoff_ms: float = Field(default=8_000, gt=0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    jitter: bool = True

    @model_validator(mode="after")
    def _validate_backoff_bounds(self) -> Self:
        if self.initial_backoff_ms <= self.max_backoff_ms:
            return self
        # Only reject explicit conflicts; a default on the unset side must not
        # invalidate a config that was valid before cross-field validation.
        # The explicit value always wins, so the unset side moves to meet it
        # in either direction -- see docs/configuration.md.
        if {"initial_backoff_ms", "max_backoff_ms"} <= self.model_fields_set:
            raise ValueError("initial_backoff_ms must not exceed max_backoff_ms")
        if "initial_backoff_ms" in self.model_fields_set:
            self.max_backoff_ms = self.initial_backoff_ms
        else:
            self.initial_backoff_ms = self.max_backoff_ms
        return self


class ProviderRegistration(BaseModel):
    """Configuration for one registered provider."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    plugin_id: ProviderId
    config: dict[str, Any]
    rate_limit_rps: float | None = Field(default=None, gt=0)
    timeout_ms: float | None = Field(default=None, gt=0)
    max_requests_per_day: int | None = Field(default=None, ge=1)
    retry: RetryPolicy | None = None
    enabled: bool = True


class RateLimitConfig(BaseModel):
    """Global rate-limiting policy."""

    max_in_flight: int = Field(
        default=10,
        ge=1,
        validation_alias=AliasChoices("max_in_flight", "max_concurrent"),
    )
    max_requests_per_second: float = Field(default=20, gt=0)


class HTTPConfig(BaseModel):
    """Shared HTTP client settings."""

    max_connections: int = Field(default=20, ge=1)
    max_keepalive_connections: int = Field(default=10, ge=0)
    connect_timeout_ms: float = Field(default=5_000, gt=0)
    cache_enabled: bool = True
    cache_max_entries: int = Field(default=256, ge=1)
    raw_archive_enabled: bool = Field(
        default=True,
        description="Kill switch for raw payload archiving",
    )
    raw_archive_path: str | None = Field(
        default=None,
        description=(
            "Gzipped JSONL file recording every network response; archiving "
            "is active only when a path is set"
        ),
    )

    @model_validator(mode="after")
    def _validate_connection_bounds(self) -> Self:
        if self.max_keepalive_connections <= self.max_connections:
            return self
        # Only reject explicit conflicts; a default on the unset side must not
        # invalidate a config that was valid before cross-field validation.
        # The explicit value always wins, so setting only the keepalive cap
        # raises max_connections above its default -- see docs/configuration.md.
        if {"max_connections", "max_keepalive_connections"} <= self.model_fields_set:
            raise ValueError(
                "max_keepalive_connections must not exceed max_connections",
            )
        if "max_keepalive_connections" in self.model_fields_set:
            self.max_connections = self.max_keepalive_connections
        else:
            self.max_keepalive_connections = self.max_connections
        return self


class OmniWeatherConfig(BaseModel):
    """Top-level client configuration."""

    providers: list[ProviderRegistration]
    rate_limiting: RateLimitConfig = Field(default_factory=RateLimitConfig)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    http: HTTPConfig = Field(default_factory=HTTPConfig)
    default_timeout_ms: float = Field(default=10_000, gt=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    sqlite: str | None = None
    granularity: list[Granularity] = Field(
        default_factory=lambda: [Granularity.HOURLY, Granularity.DAILY],
    )
    language: str = "en"
    include_raw: bool = False
    debug: bool = False

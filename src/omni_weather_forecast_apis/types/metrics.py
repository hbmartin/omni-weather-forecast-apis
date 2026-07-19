"""Structured metric events emitted by the client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from omni_weather_forecast_apis.types._time import normalize_utc_datetime, utc_now
from omni_weather_forecast_apis.types.schema import ErrorCode, ProviderId


class MetricKind(StrEnum):
    """Kinds of measurements the client emits."""

    REQUEST_START = "request_start"
    REQUEST_END = "request_end"
    RETRY_SCHEDULED = "retry_scheduled"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    QUOTA_CONSUMED = "quota_consumed"
    QUOTA_EXHAUSTED = "quota_exhausted"


@dataclass(frozen=True, kw_only=True, slots=True)
class MetricEvent:
    """One measurement emitted by the client.

    ``provider`` is ``None`` for cache events, which are observed at the
    shared HTTP transport where no per-provider attribution exists; those
    events carry the request ``url`` instead.
    """

    kind: MetricKind
    provider: ProviderId | None = None
    timestamp: datetime = field(default_factory=utc_now)
    attempt: int | None = None
    latency_ms: float | None = None
    error_code: ErrorCode | None = None
    http_status: int | None = None
    url: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timestamp",
            normalize_utc_datetime(self.timestamp),
        )


type MetricsHook = Callable[[MetricEvent], None]

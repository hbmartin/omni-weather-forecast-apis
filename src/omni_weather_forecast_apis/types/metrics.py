"""Structured metric events emitted by the client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from omni_weather_forecast_apis.types.schema import ErrorCode, ProviderId


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MetricKind(StrEnum):
    """Kinds of measurements the client emits."""

    REQUEST_START = "request_start"
    REQUEST_END = "request_end"
    RETRY_SCHEDULED = "retry_scheduled"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    QUOTA_CONSUMED = "quota_consumed"
    QUOTA_EXHAUSTED = "quota_exhausted"


@dataclass(frozen=True, slots=True)
class MetricEvent:
    """One measurement emitted by the client.

    ``provider`` is ``None`` for cache events, which are observed at the
    shared HTTP transport where no per-provider attribution exists; those
    events carry the request ``url`` instead.
    """

    kind: MetricKind
    provider: ProviderId | None = None
    timestamp: datetime = field(default_factory=_utc_now)
    attempt: int | None = None
    latency_ms: float | None = None
    error_code: ErrorCode | None = None
    http_status: int | None = None
    url: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


type MetricsHook = Callable[[MetricEvent], None]

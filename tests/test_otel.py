from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from omni_weather_forecast_apis.otel import create_otel_metrics_hook
from omni_weather_forecast_apis.types import (
    ErrorCode,
    MetricEvent,
    MetricKind,
    ProviderId,
)


class RecordingInstrument:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, str]]] = []

    def add(self, value: float, attributes: dict[str, str]) -> None:
        self.calls.append((value, attributes))

    def record(self, value: float, attributes: dict[str, str]) -> None:
        self.calls.append((value, attributes))


class RecordingMeter:
    def __init__(self) -> None:
        self.instruments: dict[str, RecordingInstrument] = {}

    def create_counter(self, name: str, **_kwargs: Any) -> RecordingInstrument:
        return self._create_instrument(name)

    def create_histogram(self, name: str, **_kwargs: Any) -> RecordingInstrument:
        return self._create_instrument(name)

    def _create_instrument(self, name: str) -> RecordingInstrument:
        instrument = RecordingInstrument()
        self.instruments[name] = instrument
        return instrument


def test_otel_bridge_records_every_metric_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meter = RecordingMeter()
    provider = object()
    get_meter_calls: list[tuple[str, object]] = []
    metrics = ModuleType("opentelemetry.metrics")

    def get_meter(name: str, *, meter_provider: object) -> RecordingMeter:
        get_meter_calls.append((name, meter_provider))
        return meter

    metrics.get_meter = get_meter  # type: ignore[attr-defined]
    opentelemetry = ModuleType("opentelemetry")
    opentelemetry.metrics = metrics  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry", opentelemetry)

    hook = create_otel_metrics_hook(provider)
    hook(MetricEvent(kind=MetricKind.REQUEST_START))
    hook(
        MetricEvent(
            kind=MetricKind.REQUEST_END,
            provider=ProviderId.OPEN_METEO,
            latency_ms=12.5,
        ),
    )
    hook(
        MetricEvent(
            kind=MetricKind.REQUEST_END,
            error_code=ErrorCode.NETWORK,
        ),
    )
    hook(
        MetricEvent(
            kind=MetricKind.RETRY_SCHEDULED,
            provider=ProviderId.OPEN_METEO,
            error_code=ErrorCode.TIMEOUT,
        ),
    )
    hook(MetricEvent(kind=MetricKind.RETRY_SCHEDULED))
    hook(MetricEvent(kind=MetricKind.CACHE_HIT, extra={"outcome": "hit"}))
    hook(MetricEvent(kind=MetricKind.CACHE_MISS))
    hook(
        MetricEvent(
            kind=MetricKind.QUOTA_CONSUMED,
            provider=ProviderId.OPEN_METEO,
        ),
    )
    hook(MetricEvent(kind=MetricKind.QUOTA_EXHAUSTED))

    assert get_meter_calls == [("omni_weather_forecast_apis", provider)]
    assert meter.instruments["omni_weather.requests"].calls == [
        (1, {"provider": "open_meteo", "outcome": "success"}),
        (1, {"outcome": "network"}),
    ]
    assert meter.instruments["omni_weather.request.duration_ms"].calls == [
        (12.5, {"provider": "open_meteo"}),
    ]
    assert meter.instruments["omni_weather.retries"].calls == [
        (1, {"provider": "open_meteo", "error_code": "timeout"}),
        (1, {"error_code": "unknown"}),
    ]
    assert meter.instruments["omni_weather.cache"].calls == [
        (1, {"outcome": "hit"}),
        (1, {"outcome": ""}),
    ]
    assert meter.instruments["omni_weather.quota.consumed"].calls == [
        (1, {"provider": "open_meteo"}),
    ]
    assert meter.instruments["omni_weather.quota.exhausted"].calls == [(1, {})]

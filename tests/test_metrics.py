"""Tests for the MetricsHook observability layer."""

from __future__ import annotations

import asyncio
import builtins
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx2
import pytest

from omni_weather_forecast_apis.client import OmniWeatherClient
from omni_weather_forecast_apis.http_cache import CachingTransport
from omni_weather_forecast_apis.otel import create_otel_metrics_hook
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ForecastRequest,
    MetricEvent,
    MetricKind,
    OmniWeatherConfig,
    ProviderId,
    ProviderRegistration,
    RetryPolicy,
)
from tests.helpers import DummyPlugin, FlakyInstance


def _run_forecast(
    instance: Any,
    events: list[MetricEvent],
    *,
    max_attempts: int = 3,
    max_requests_per_day: int | None = None,
    extra_hooks: list[Any] | None = None,
) -> Any:
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                    max_requests_per_day=max_requests_per_day,
                ),
            ],
            retry=RetryPolicy(
                max_attempts=max_attempts,
                initial_backoff_ms=1,
                jitter=False,
            ),
        ),
        plugins=[DummyPlugin(ProviderId.OPEN_METEO, instance)],
        metrics_hooks=[events.append, *(extra_hooks or [])],
    )

    async def scenario() -> Any:
        await client.initialize()
        try:
            return await client.forecast(
                ForecastRequest(latitude=34, longitude=-118),
            )
        finally:
            await client.close()

    return asyncio.run(scenario())


def _kinds(events: list[MetricEvent]) -> list[MetricKind]:
    return [event.kind for event in events]


def test_success_emits_start_and_end_events() -> None:
    events: list[MetricEvent] = []

    response = _run_forecast(FlakyInstance(failures=0), events)

    assert response.results[0].status == "success"
    assert _kinds(events) == [MetricKind.REQUEST_START, MetricKind.REQUEST_END]
    start, end = events
    assert start.provider == ProviderId.OPEN_METEO
    assert start.attempt == 1
    assert end.error_code is None
    assert end.latency_ms is not None
    assert end.latency_ms >= 0
    assert response.summary.retries == 0


def test_retries_emit_retry_scheduled_and_count_on_summary() -> None:
    events: list[MetricEvent] = []

    response = _run_forecast(FlakyInstance(failures=2), events)

    assert response.results[0].status == "success"
    retry_events = [e for e in events if e.kind is MetricKind.RETRY_SCHEDULED]
    assert [e.attempt for e in retry_events] == [1, 2]
    assert all(e.error_code is ErrorCode.NETWORK for e in retry_events)
    assert all("delay_seconds" in e.extra for e in retry_events)
    end_events = [e for e in events if e.kind is MetricKind.REQUEST_END]
    assert [e.error_code for e in end_events] == [
        ErrorCode.NETWORK,
        ErrorCode.NETWORK,
        None,
    ]
    assert response.summary.retries == 2


def test_quota_events_are_emitted() -> None:
    events: list[MetricEvent] = []

    _run_forecast(
        FlakyInstance(failures=0),
        events,
        max_attempts=1,
        max_requests_per_day=1,
    )
    consumed = [e for e in events if e.kind is MetricKind.QUOTA_CONSUMED]
    assert len(consumed) == 1
    assert consumed[0].extra == {"limit": 1}

    events.clear()
    instance = FlakyInstance(failures=0)
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                    max_requests_per_day=1,
                ),
            ],
            retry=RetryPolicy(max_attempts=1),
        ),
        plugins=[DummyPlugin(ProviderId.OPEN_METEO, instance)],
        metrics_hooks=[events.append],
    )

    async def scenario() -> None:
        await client.initialize()
        await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()

    asyncio.run(scenario())

    assert _kinds(events).count(MetricKind.QUOTA_CONSUMED) == 1
    exhausted = [e for e in events if e.kind is MetricKind.QUOTA_EXHAUSTED]
    assert len(exhausted) == 1
    assert exhausted[0].error_code is ErrorCode.QUOTA_EXCEEDED


def test_raising_metrics_hook_is_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    events: list[MetricEvent] = []

    def bad_hook(event: MetricEvent) -> None:
        del event
        raise RuntimeError("metrics sink down")

    with caplog.at_level("ERROR", logger="omni_weather_forecast_apis"):
        response = _run_forecast(
            FlakyInstance(failures=0),
            events,
            extra_hooks=[bad_hook],
        )

    assert response.results[0].status == "success"
    assert len(events) == 2
    assert "Metrics hook failed" in caplog.text


def test_caching_transport_reports_cache_outcomes() -> None:
    outcomes: list[tuple[str, str]] = []
    call_count = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal call_count
        call_count += 1
        if request.headers.get("If-None-Match") == '"v1"':
            return httpx2.Response(304, headers={"ETag": '"v1"'})
        return httpx2.Response(
            200,
            headers={"ETag": '"v1"', "Cache-Control": "max-age=1000"},
            json={"ok": call_count},
        )

    transport = CachingTransport(
        httpx2.MockTransport(handler),
        on_cache_event=lambda url, outcome: outcomes.append((url, outcome)),
    )

    async def scenario() -> None:
        async with httpx2.AsyncClient(transport=transport) as client:
            await client.get("https://api.example.com/data")
            await client.get("https://api.example.com/data")
            await client.get("https://api.example.com/other")

    asyncio.run(scenario())

    assert [outcome for _url, outcome in outcomes] == ["store", "hit", "store"]
    assert outcomes[0][0] == "https://api.example.com/data"


def test_caching_transport_reports_miss_for_uncacheable() -> None:
    outcomes: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        del request
        return httpx2.Response(200, headers={"Cache-Control": "no-store"}, json={})

    transport = CachingTransport(
        httpx2.MockTransport(handler),
        on_cache_event=lambda _url, outcome: outcomes.append(outcome),
    )

    async def scenario() -> None:
        async with httpx2.AsyncClient(transport=transport) as client:
            await client.get("https://api.example.com/data")

    asyncio.run(scenario())

    assert outcomes == ["miss"]


def test_otel_bridge_requires_opentelemetry() -> None:
    pytest.importorskip("opentelemetry")


def test_otel_bridge_raises_without_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("opentelemetry"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError, match=r"omni-weather-forecast-apis\[otel\]"):
        create_otel_metrics_hook()


def test_metric_event_rejects_positional_construction() -> None:
    """Keyword-only construction makes field misbinding structurally impossible."""

    with pytest.raises(TypeError, match="positional"):
        MetricEvent(MetricKind.REQUEST_START)


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        (
            datetime(2026, 7, 18, 12),  # noqa: DTZ001  # naive input is the point
            datetime(2026, 7, 18, 12, tzinfo=UTC),
        ),
        (
            datetime(2026, 7, 18, 12, tzinfo=timezone(timedelta(hours=-5))),
            datetime(2026, 7, 18, 17, tzinfo=UTC),
        ),
    ],
)
def test_metric_event_normalizes_timestamp_to_utc(
    supplied: datetime,
    expected: datetime,
) -> None:
    """Naive input is assumed UTC; aware input is converted, preserving the instant."""

    event = MetricEvent(kind=MetricKind.REQUEST_START, timestamp=supplied)

    assert event.timestamp == expected
    assert event.timestamp.tzinfo == UTC


def test_metric_event_is_frozen() -> None:
    event = MetricEvent(kind=MetricKind.REQUEST_START)

    with pytest.raises(FrozenInstanceError):
        event.latency_ms = 1.0

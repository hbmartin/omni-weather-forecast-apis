"""Tests for retry-with-backoff behavior in the client."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from omni_weather_forecast_apis.client import (
    OmniWeatherClient,
    _compute_backoff_seconds,
)
from omni_weather_forecast_apis.plugins._base import parse_retry_after
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ForecastRequest,
    OmniWeatherConfig,
    ProviderId,
    ProviderLogEvent,
    ProviderRegistration,
    ProviderSuccess,
    RetryPolicy,
)
from tests.helpers import DummyPlugin, FlakyInstance

FAST_RETRIES = RetryPolicy(
    max_attempts=3,
    initial_backoff_ms=1,
    max_backoff_ms=2,
    jitter=False,
)


def _client_for(
    instance: Any,
    *,
    retry: RetryPolicy = FAST_RETRIES,
    log_hooks: list[Any] | None = None,
) -> OmniWeatherClient:
    return OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(plugin_id=ProviderId.OPEN_METEO, config={}),
            ],
            retry=retry,
        ),
        plugins=[DummyPlugin(ProviderId.OPEN_METEO, instance)],
        log_hooks=log_hooks,
    )


def test_retryable_error_is_retried_until_success() -> None:
    instance = FlakyInstance(failures=2)
    events: list[ProviderLogEvent] = []
    client = _client_for(instance, log_hooks=[events.append])

    async def scenario() -> ProviderSuccess:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        result = response.results[0]
        assert isinstance(result, ProviderSuccess)
        return result

    asyncio.run(scenario())

    assert instance.calls == 3
    assert sum(event.phase == "retry" for event in events) == 2


def test_retries_stop_at_max_attempts() -> None:
    instance = FlakyInstance(failures=10)
    client = _client_for(instance)

    async def scenario() -> str:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        return response.results[0].error.code.value

    error_code = asyncio.run(scenario())

    assert error_code == ErrorCode.NETWORK.value
    assert instance.calls == 3


def test_non_retryable_error_is_not_retried() -> None:
    instance = FlakyInstance(failures=10, code=ErrorCode.AUTH_FAILED)
    client = _client_for(instance)

    async def scenario() -> str:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        return response.results[0].error.code.value

    error_code = asyncio.run(scenario())

    assert error_code == ErrorCode.AUTH_FAILED.value
    assert instance.calls == 1


def test_per_provider_retry_policy_overrides_global() -> None:
    instance = FlakyInstance(failures=10)
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                    retry=RetryPolicy(max_attempts=1),
                ),
            ],
            retry=FAST_RETRIES,
        ),
        plugins=[DummyPlugin(ProviderId.OPEN_METEO, instance)],
    )

    async def scenario() -> None:
        await client.initialize()
        await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()

    asyncio.run(scenario())

    assert instance.calls == 1


def test_backoff_honors_retry_after() -> None:
    policy = RetryPolicy(initial_backoff_ms=1, max_backoff_ms=2, jitter=False)

    delay = _compute_backoff_seconds(policy, attempt=1, retry_after_seconds=0.5)

    assert delay == 0.5


def test_backoff_gives_up_on_excessive_retry_after() -> None:
    policy = RetryPolicy(initial_backoff_ms=1, max_backoff_ms=2, jitter=False)

    delay = _compute_backoff_seconds(policy, attempt=1, retry_after_seconds=3600)

    assert delay is None


def test_provider_retry_after_passes_through_unclamped() -> None:
    # The client's backoff policy alone decides whether an excessive
    # Retry-After abandons retries; plugins must report the raw value.
    assert parse_retry_after("3600") == 3600.0


def test_backoff_grows_exponentially_and_caps() -> None:
    policy = RetryPolicy(
        initial_backoff_ms=100,
        max_backoff_ms=300,
        backoff_multiplier=2.0,
        jitter=False,
    )

    assert _compute_backoff_seconds(policy, 1, None) == pytest.approx(0.1)
    assert _compute_backoff_seconds(policy, 2, None) == pytest.approx(0.2)
    assert _compute_backoff_seconds(policy, 3, None) == pytest.approx(0.3)
    assert _compute_backoff_seconds(policy, 4, None) == pytest.approx(0.3)

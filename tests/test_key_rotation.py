"""Tests for multi-API-key fallback with sticky rotation in the client."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from omni_weather_forecast_apis.client import OmniWeatherClient
from omni_weather_forecast_apis.plugins.openweather import openweather_plugin
from omni_weather_forecast_apis.plugins.pirate_weather import pirate_weather_plugin
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ForecastRequest,
    MetricEvent,
    MetricKind,
    OmniWeatherConfig,
    ProviderId,
    ProviderLogEvent,
    ProviderRegistration,
    ProviderResult,
    ProviderSuccess,
    RetryPolicy,
)
from tests.helpers import FactoryPlugin, KeyScriptedInstance

FAST_RETRIES = RetryPolicy(
    max_attempts=3,
    initial_backoff_ms=1,
    max_backoff_ms=2,
    jitter=False,
)


def _scripted_factory(
    failing_keys: set[str],
    call_log: list[str],
    code: ErrorCode = ErrorCode.AUTH_FAILED,
) -> Callable[[dict[str, Any]], KeyScriptedInstance]:
    return lambda config: KeyScriptedInstance(
        config["api_key"],
        failing_keys,
        call_log,
        code=code,
    )


def _rotation_client(
    api_key: str | list[str],
    factory: Callable[[dict[str, Any]], Any],
    *,
    retry: RetryPolicy = FAST_RETRIES,
    log_hooks: list[Any] | None = None,
    metrics_hooks: list[Any] | None = None,
    max_requests_per_day: int | None = None,
) -> tuple[OmniWeatherClient, FactoryPlugin]:
    plugin = FactoryPlugin(ProviderId.OPEN_METEO, factory)
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={"api_key": api_key},
                    max_requests_per_day=max_requests_per_day,
                ),
            ],
            retry=retry,
        ),
        plugins=[plugin],
        log_hooks=log_hooks,
        metrics_hooks=metrics_hooks,
    )
    return client, plugin


def _single_forecast(client: OmniWeatherClient) -> ProviderResult:
    async def scenario() -> ProviderResult:
        async with client:
            response = await client.forecast(
                ForecastRequest(latitude=34, longitude=-118),
            )
        return response.results[0]

    return asyncio.run(scenario())


def _rotation_metrics(events: list[MetricEvent]) -> list[MetricEvent]:
    return [event for event in events if event.kind is MetricKind.KEY_ROTATED]


def test_list_key_initializes_one_instance_per_key() -> None:
    call_log: list[str] = []
    client, plugin = _rotation_client(
        ["k1", "k2"],
        _scripted_factory(set(), call_log),
    )

    result = _single_forecast(client)

    assert isinstance(result, ProviderSuccess)
    assert plugin.initialize_calls == 2
    assert call_log == ["k1"]


@pytest.mark.parametrize(
    "code",
    [
        ErrorCode.AUTH_FAILED,
        ErrorCode.PARSE,
        ErrorCode.NO_DATA,
        ErrorCode.UNKNOWN,
        ErrorCode.QUOTA_EXCEEDED,
    ],
)
def test_nonretryable_failure_rotates_immediately(code: ErrorCode) -> None:
    call_log: list[str] = []
    client, _plugin = _rotation_client(
        ["k1", "k2"],
        _scripted_factory({"k1"}, call_log, code=code),
    )

    result = _single_forecast(client)

    assert isinstance(result, ProviderSuccess)
    assert call_log == ["k1", "k2"]


def test_retryable_failure_exhausts_key_budget_before_rotating() -> None:
    call_log: list[str] = []
    client, _plugin = _rotation_client(
        ["k1", "k2"],
        _scripted_factory({"k1"}, call_log, code=ErrorCode.NETWORK),
    )

    result = _single_forecast(client)

    assert isinstance(result, ProviderSuccess)
    assert call_log == ["k1", "k1", "k1", "k2"]


def test_sticky_promotion_across_requests() -> None:
    call_log: list[str] = []
    client, _plugin = _rotation_client(
        ["k1", "k2"],
        _scripted_factory({"k1"}, call_log),
    )

    async def scenario() -> None:
        await client.initialize()
        await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        call_log.clear()
        await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()

    asyncio.run(scenario())

    assert call_log == ["k2"]


def test_sticky_failure_wraps_around_to_recovered_key() -> None:
    call_log: list[str] = []
    failing_keys = {"k1"}
    client, _plugin = _rotation_client(
        ["k1", "k2", "k3"],
        _scripted_factory(failing_keys, call_log),
    )

    async def scenario() -> None:
        async with client:
            await client.forecast(ForecastRequest(latitude=34, longitude=-118))
            assert call_log == ["k1", "k2"]
            failing_keys.clear()
            failing_keys.update({"k2", "k3"})
            call_log.clear()
            await client.forecast(ForecastRequest(latitude=34, longitude=-118))
            assert call_log == ["k2", "k3", "k1"]
            call_log.clear()
            await client.forecast(ForecastRequest(latitude=34, longitude=-118))

    asyncio.run(scenario())

    assert call_log == ["k1"]


def test_all_keys_fail_returns_last_error_annotated() -> None:
    codes = {"k1": ErrorCode.AUTH_FAILED, "k2": ErrorCode.PARSE}
    call_log: list[str] = []
    metric_events: list[MetricEvent] = []
    client, _plugin = _rotation_client(
        ["k1", "k2"],
        lambda config: KeyScriptedInstance(
            config["api_key"],
            {"k1", "k2"},
            call_log,
            code=codes[config["api_key"]],
        ),
        metrics_hooks=[metric_events.append],
    )

    result = _single_forecast(client)

    assert result.status == "error"
    assert result.error.code is ErrorCode.PARSE
    assert result.error.message.endswith("(all 2 API keys failed)")
    assert call_log == ["k1", "k2"]
    assert len(_rotation_metrics(metric_events)) == 1


def test_empty_key_list_is_init_error() -> None:
    client, plugin = _rotation_client([], _scripted_factory(set(), []))

    result = _single_forecast(client)

    assert result.status == "error"
    assert result.error.code is ErrorCode.NOT_AVAILABLE
    assert "api_key list must not be empty" in result.error.message
    assert plugin.initialize_calls == 0


def test_invalid_list_entries_are_init_errors() -> None:
    client, plugin = _rotation_client(["k1", ""], _scripted_factory(set(), []))

    result = _single_forecast(client)

    assert result.status == "error"
    assert result.error.code is ErrorCode.NOT_AVAILABLE
    assert "position(s): 2" in result.error.message
    assert plugin.initialize_calls == 0


def test_single_item_list_emits_no_rotation_events() -> None:
    log_events: list[ProviderLogEvent] = []
    metric_events: list[MetricEvent] = []
    client, _plugin = _rotation_client(
        ["k1"],
        _scripted_factory({"k1"}, []),
        log_hooks=[log_events.append],
        metrics_hooks=[metric_events.append],
    )

    result = _single_forecast(client)

    assert result.status == "error"
    assert "API keys failed" not in result.error.message
    assert not _rotation_metrics(metric_events)
    assert not [event for event in log_events if "rotating" in event.message]


def test_rotation_events_never_contain_key_material() -> None:
    log_events: list[ProviderLogEvent] = []
    metric_events: list[MetricEvent] = []
    client, _plugin = _rotation_client(
        ["secret-key-one", "secret-key-two"],
        _scripted_factory({"secret-key-one"}, []),
        log_hooks=[log_events.append],
        metrics_hooks=[metric_events.append],
    )

    result = _single_forecast(client)

    assert isinstance(result, ProviderSuccess)
    observable = [
        *(f"{event.message} {dict(event.extra)}" for event in log_events),
        *(str(dict(event.extra)) for event in metric_events),
    ]
    assert all("secret-key" not in text for text in observable)
    rotations = _rotation_metrics(metric_events)
    assert [dict(event.extra) for event in rotations] == [
        {"from_key": 1, "to_key": 2, "key_count": 2},
    ]


def test_rotation_events_do_not_share_mutable_extra() -> None:
    log_events: list[ProviderLogEvent] = []

    def mutate_metric_extra(event: MetricEvent) -> None:
        if event.kind is MetricKind.KEY_ROTATED and isinstance(event.extra, dict):
            event.extra["from_key"] = 99

    client, _plugin = _rotation_client(
        ["k1", "k2"],
        _scripted_factory({"k1"}, []),
        log_hooks=[log_events.append],
        metrics_hooks=[mutate_metric_extra],
    )

    result = _single_forecast(client)

    assert isinstance(result, ProviderSuccess)
    rotation_logs = [event for event in log_events if "rotating" in event.message]
    assert [dict(event.extra) for event in rotation_logs] == [
        {"from_key": 1, "to_key": 2, "key_count": 2},
    ]


def test_quota_gate_rejection_does_not_rotate() -> None:
    call_log: list[str] = []
    metric_events: list[MetricEvent] = []
    client, _plugin = _rotation_client(
        ["k1", "k2"],
        _scripted_factory(set(), call_log),
        metrics_hooks=[metric_events.append],
        max_requests_per_day=1,
    )

    async def scenario() -> ProviderResult:
        await client.initialize()
        await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        return response.results[0]

    result = asyncio.run(scenario())

    assert result.status == "error"
    assert result.error.code is ErrorCode.QUOTA_EXCEEDED
    assert "API keys failed" not in result.error.message
    assert call_log == ["k1"]
    assert not _rotation_metrics(metric_events)


def test_rotation_attempts_consume_shared_provider_quota() -> None:
    call_log: list[str] = []
    metric_events: list[MetricEvent] = []
    client, _plugin = _rotation_client(
        ["k1", "k2"],
        _scripted_factory(
            {"k1", "k2"},
            call_log,
            code=ErrorCode.NETWORK,
        ),
        metrics_hooks=[metric_events.append],
        max_requests_per_day=4,
    )

    result = _single_forecast(client)

    assert result.status == "error"
    assert result.error.code is ErrorCode.QUOTA_EXCEEDED
    assert call_log == ["k1", "k1", "k1", "k2"]
    assert sum(event.kind is MetricKind.QUOTA_CONSUMED for event in metric_events) == 4
    assert sum(event.kind is MetricKind.QUOTA_EXHAUSTED for event in metric_events) == 1


def test_rotation_does_not_count_as_summary_retry() -> None:
    client, _plugin = _rotation_client(
        ["k1", "k2"],
        _scripted_factory({"k1"}, []),
    )

    async def scenario() -> int:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        return response.summary.retries

    assert asyncio.run(scenario()) == 0


_OPENWEATHER_PAYLOAD = {
    "timezone": "America/Los_Angeles",
    "hourly": [
        {
            "dt": 1704067200,
            "temp": 20.0,
            "feels_like": 18.0,
            "humidity": 65,
            "wind_speed": 5.0,
            "pressure": 1013,
            "clouds": 50,
            "weather": [{"id": 800, "description": "clear sky"}],
        },
    ],
}

_PIRATE_WEATHER_PAYLOAD = {
    "timezone": "America/Los_Angeles",
    "hourly": {
        "data": [
            {
                "time": 1704067200,
                "temperature": 20.0,
                "weatherCode": 0,
            },
        ],
    },
}


def _real_provider_result(
    plugin: Any,
    provider_id: ProviderId,
    handler: Callable[[httpx2.Request], httpx2.Response],
) -> ProviderResult:
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=provider_id,
                    config={"api_key": ["k1", "k2"]},
                ),
            ],
            retry=FAST_RETRIES,
        ),
        plugins=[plugin],
    )

    async def scenario() -> ProviderResult:
        client._http_client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler),
        )
        try:
            await client.initialize()
            response = await client.forecast(
                ForecastRequest(latitude=34, longitude=-118),
            )
            return response.results[0]
        finally:
            await client.close()

    return asyncio.run(scenario())


def test_openweather_second_key_used_after_401() -> None:
    observed_keys: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        key = request.url.params["appid"]
        observed_keys.append(key)
        if key == "k1":
            return httpx2.Response(401, json={"message": "unauthorized"})
        return httpx2.Response(200, json=_OPENWEATHER_PAYLOAD)

    result = _real_provider_result(
        openweather_plugin,
        ProviderId.OPENWEATHER,
        handler,
    )

    assert isinstance(result, ProviderSuccess)
    assert observed_keys == ["k1", "k2"]


def test_pirate_weather_url_path_rebuilt_per_key() -> None:
    observed_paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        observed_paths.append(request.url.path)
        if "/k1/" in request.url.path:
            return httpx2.Response(403, json={"message": "forbidden"})
        return httpx2.Response(200, json=_PIRATE_WEATHER_PAYLOAD)

    result = _real_provider_result(
        pirate_weather_plugin,
        ProviderId.PIRATE_WEATHER,
        handler,
    )

    assert isinstance(result, ProviderSuccess)
    assert len(observed_paths) == 2
    assert "/k1/" in observed_paths[0]
    assert "/k2/" in observed_paths[1]

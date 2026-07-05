"""Tests for daily quota tracking and enforcement."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from omni_weather_forecast_apis.client import OmniWeatherClient
from omni_weather_forecast_apis.quota import (
    InMemoryQuotaTracker,
    QuotaTracker,
    SqliteQuotaTracker,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ForecastRequest,
    OmniWeatherConfig,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
    ProviderId,
    ProviderRegistration,
    RetryPolicy,
)


class CountingInstance:
    provider_id = ProviderId.OPEN_METEO

    def __init__(self) -> None:
        self.calls = 0

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(requires_api_key=False)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        del params, client
        self.calls += 1
        return PluginFetchSuccess(forecasts=[])


class DummyPlugin:
    def __init__(self, provider_id: ProviderId, instance: Any) -> None:
        self._provider_id = provider_id
        self._instance = instance

    @property
    def id(self) -> ProviderId:
        return self._provider_id

    @property
    def name(self) -> str:
        return self._provider_id.value

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return config

    async def initialize(self, config: dict[str, Any]) -> Any:
        del config
        return self._instance


def test_in_memory_tracker_counts_per_provider_and_day() -> None:
    tracker = InMemoryQuotaTracker()
    day = date(2026, 7, 3)
    other_day = date(2026, 7, 4)

    tracker.record_request(ProviderId.OPENWEATHER, day)
    tracker.record_request(ProviderId.OPENWEATHER, day)
    tracker.record_request(ProviderId.NWS, day)

    assert tracker.get_usage(ProviderId.OPENWEATHER, day) == 2
    assert tracker.get_usage(ProviderId.NWS, day) == 1
    assert tracker.get_usage(ProviderId.OPENWEATHER, other_day) == 0


def test_in_memory_tracker_try_consume_respects_limit() -> None:
    tracker = InMemoryQuotaTracker()
    day = date(2026, 7, 3)

    assert tracker.try_consume(ProviderId.OPENWEATHER, day, 2)
    assert tracker.try_consume(ProviderId.OPENWEATHER, day, 2)
    assert not tracker.try_consume(ProviderId.OPENWEATHER, day, 2)
    assert tracker.get_usage(ProviderId.OPENWEATHER, day) == 2


def test_sqlite_tracker_persists_across_instances(tmp_path: Path) -> None:
    database = tmp_path / "quota.sqlite"
    day = date(2026, 7, 3)

    first = SqliteQuotaTracker(database)
    first.record_request(ProviderId.OPENWEATHER, day)
    first.record_request(ProviderId.OPENWEATHER, day)

    second = SqliteQuotaTracker(database)
    assert second.get_usage(ProviderId.OPENWEATHER, day) == 2
    assert isinstance(second, QuotaTracker)


def test_sqlite_tracker_try_consume_is_atomic(tmp_path: Path) -> None:
    tracker = SqliteQuotaTracker(tmp_path / "quota.sqlite")
    day = date(2026, 7, 3)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _item: tracker.try_consume(ProviderId.OPENWEATHER, day, 3),
                range(12),
            ),
        )

    assert results.count(True) == 3
    assert results.count(False) == 9
    assert tracker.get_usage(ProviderId.OPENWEATHER, day) == 3


def test_client_enforces_daily_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = CountingInstance()
    registry = {ProviderId.OPEN_METEO: DummyPlugin(ProviderId.OPEN_METEO, instance)}
    monkeypatch.setattr(
        "omni_weather_forecast_apis.client.get_plugin_registry",
        lambda: registry,
    )
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                    max_requests_per_day=2,
                ),
            ],
            retry=RetryPolicy(max_attempts=1),
        ),
    )

    async def scenario() -> list[str]:
        await client.initialize()
        statuses: list[str] = []
        for _ in range(3):
            response = await client.forecast(
                ForecastRequest(latitude=34, longitude=-118),
            )
            result = response.results[0]
            if result.status == "error":
                statuses.append(result.error.code.value)
            else:
                statuses.append(result.status)
        await client.close()
        return statuses

    statuses = asyncio.run(scenario())

    assert statuses == ["success", "success", ErrorCode.QUOTA_EXCEEDED.value]
    assert instance.calls == 2

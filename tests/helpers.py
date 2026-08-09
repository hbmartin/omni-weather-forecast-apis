"""Shared test doubles for client/orchestrator tests.

These replace the near-identical DummyPlugin/instance stubs that were
previously copy-pasted across the client test modules. Provider parser
tests intentionally stay self-contained and do not use these helpers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx2

from omni_weather_forecast_apis.types import (
    ErrorCode,
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
    ProviderId,
)


class DummyPlugin:
    """Minimal WeatherPlugin double wrapping a prebuilt instance."""

    def __init__(self, provider_id: ProviderId, instance: Any) -> None:
        self._provider_id = provider_id
        self._instance = instance
        self.initialize_calls = 0

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
        self.initialize_calls += 1
        return self._instance


class FactoryPlugin:
    """WeatherPlugin double that builds a fresh instance per initialize call.

    Needed for API-key-pool tests, where the client initializes one instance
    per configured key.
    """

    def __init__(
        self,
        provider_id: ProviderId,
        factory: Callable[[dict[str, Any]], Any],
    ) -> None:
        self._provider_id = provider_id
        self._factory = factory
        self.initialize_calls = 0

    @property
    def id(self) -> ProviderId:
        return self._provider_id

    @property
    def name(self) -> str:
        return self._provider_id.value

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return config

    async def initialize(self, config: dict[str, Any]) -> Any:
        self.initialize_calls += 1
        return self._factory(config)


class KeyScriptedInstance:
    """Records its key per fetch; fails while the key is in ``failing_keys``.

    ``failing_keys`` and ``call_log`` are shared across the instances of one
    pool, so tests can flip a key's health mid-test and observe the exact
    key order the client tried.
    """

    def __init__(
        self,
        key: str,
        failing_keys: set[str],
        call_log: list[str],
        code: ErrorCode = ErrorCode.AUTH_FAILED,
    ) -> None:
        self.key = key
        self.failing_keys = failing_keys
        self.call_log = call_log
        self.code = code

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(requires_api_key=True)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        del params, client
        self.call_log.append(self.key)
        if self.key in self.failing_keys:
            return PluginFetchError(code=self.code, message="scripted key failure")
        return PluginFetchSuccess(forecasts=[])


class CountingInstance:
    """Succeeds with an empty forecast, counting invocations."""

    def __init__(self, provider_id: ProviderId = ProviderId.OPEN_METEO) -> None:
        self.provider_id = provider_id
        self.calls = 0

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(requires_api_key=False)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        del params, client
        self.calls += 1
        return PluginFetchSuccess(forecasts=[])


class FlakyInstance:
    """Fails with a retryable error a fixed number of times, then succeeds."""

    def __init__(
        self,
        failures: int,
        code: ErrorCode = ErrorCode.NETWORK,
        provider_id: ProviderId = ProviderId.OPEN_METEO,
    ) -> None:
        self.provider_id = provider_id
        self.failures = failures
        self.code = code
        self.calls = 0

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(requires_api_key=False)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        del params, client
        self.calls += 1
        if self.calls <= self.failures:
            return PluginFetchError(code=self.code, message="transient failure")
        return PluginFetchSuccess(forecasts=[])

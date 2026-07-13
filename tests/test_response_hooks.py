"""Tests for the post-forecast response hook extension point."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx2
import pytest

from omni_weather_forecast_apis.client import OmniWeatherClient
from omni_weather_forecast_apis.types import (
    ForecastRequest,
    ForecastResponse,
    OmniWeatherConfig,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
    ProviderId,
    ProviderRegistration,
)


class SuccessInstance:
    provider_id = ProviderId.OPEN_METEO

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(requires_api_key=False)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        del params, client
        return PluginFetchSuccess(forecasts=[])


class DummyPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.OPEN_METEO

    @property
    def name(self) -> str:
        return "dummy"

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return config

    async def initialize(self, config: dict[str, Any]) -> Any:
        del config
        return SuccessInstance()


def _make_client(hooks: list[Any]) -> OmniWeatherClient:
    return OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(plugin_id=ProviderId.OPEN_METEO, config={}),
            ],
        ),
        plugins=[DummyPlugin()],
        response_hooks=hooks,
    )


def test_sync_and_async_hooks_receive_the_response() -> None:
    received: list[ForecastResponse] = []

    def sync_hook(response: ForecastResponse) -> None:
        received.append(response)

    async def async_hook(response: ForecastResponse) -> None:
        received.append(response)

    client = _make_client([sync_hook, async_hook])

    async def scenario() -> ForecastResponse:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        return response

    response = asyncio.run(scenario())

    assert received == [response, response]


def test_hook_failures_do_not_break_the_forecast(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def failing_hook(response: ForecastResponse) -> None:
        del response
        raise RuntimeError("hook exploded")

    client = _make_client([failing_hook])

    async def scenario() -> ForecastResponse:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        return response

    with caplog.at_level("ERROR", logger="omni_weather_forecast_apis"):
        response = asyncio.run(scenario())

    assert response.summary.succeeded == 1
    assert "Response hook failed" in caplog.text

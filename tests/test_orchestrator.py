from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from omni_weather_forecast_apis.client import OmniWeatherClient
from omni_weather_forecast_apis.plugins._base import build_source_forecast
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ForecastRequest,
    Granularity,
    OmniWeatherConfig,
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
    ProviderId,
    ProviderLogEvent,
    ProviderRegistration,
)


class DummyConfig(BaseModel):
    token: str = "ok"  # noqa: S105


class SuccessInstance:
    provider_id = ProviderId.OPEN_METEO

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=False,
            granularity_hourly=True,
            granularity_daily=True,
            requires_api_key=False,
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        del params, client
        forecast = build_source_forecast(ProviderId.OPEN_METEO, model="best_match")
        return PluginFetchSuccess(forecasts=[forecast], raw={"ok": True})


class ErrorInstance:
    provider_id = ProviderId.OPENWEATHER

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(requires_api_key=True)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        del params, client
        return PluginFetchError(code=ErrorCode.AUTH_FAILED, message="bad key")


class SlowInstance:
    provider_id = ProviderId.WEATHERAPI

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(requires_api_key=True)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        del params, client
        await asyncio.sleep(0.05)
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

    def validate_config(self, config: dict[str, Any]) -> DummyConfig:
        return DummyConfig.model_validate(config)

    async def initialize(self, config: DummyConfig) -> Any:
        del config
        return self._instance


def test_forecast_returns_partial_results(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = {
        ProviderId.OPEN_METEO: DummyPlugin(ProviderId.OPEN_METEO, SuccessInstance()),
        ProviderId.OPENWEATHER: DummyPlugin(ProviderId.OPENWEATHER, ErrorInstance()),
    }
    monkeypatch.setattr(
        "omni_weather_forecast_apis.client.get_plugin_registry",
        lambda: registry,
    )
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={"token": "a"},
                ),
                ProviderRegistration(
                    plugin_id=ProviderId.OPENWEATHER,
                    config={"token": "b"},
                ),
            ],
        ),
    )

    async def scenario() -> tuple[int, int, str]:
        await client.initialize()
        response = await client.forecast(
            ForecastRequest(
                latitude=34,
                longitude=-118,
                include_raw=True,
                granularity=[Granularity.HOURLY],
            ),
        )
        await client.close()
        assert response.results[0].status == "success"
        assert response.results[1].status == "error"
        return (
            response.summary.succeeded,
            response.summary.failed,
            response.completed_at.tzname() or "",
        )

    succeeded, failed, timezone_name = asyncio.run(scenario())

    assert succeeded == 1
    assert failed == 1
    assert timezone_name == "UTC"


def test_forecast_wraps_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = {
        ProviderId.WEATHERAPI: DummyPlugin(ProviderId.WEATHERAPI, SlowInstance()),
    }
    monkeypatch.setattr(
        "omni_weather_forecast_apis.client.get_plugin_registry",
        lambda: registry,
    )
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.WEATHERAPI,
                    config={"token": "a"},
                ),
            ],
            default_timeout_ms=1,
        ),
    )

    async def scenario() -> str:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        return response.results[0].error.code.value

    error_code = asyncio.run(scenario())

    assert error_code == ErrorCode.TIMEOUT.value


def test_unconfigured_requested_provider_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "omni_weather_forecast_apis.client.get_plugin_registry",
        dict,
    )
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={"token": "a"},
                ),
            ],
        ),
    )

    async def scenario() -> str:
        await client.initialize()
        response = await client.forecast(
            ForecastRequest(
                latitude=34,
                longitude=-118,
                providers=[ProviderId.WEATHERBIT],
            ),
        )
        await client.close()
        return response.results[0].error.code.value

    error_code = asyncio.run(scenario())

    assert error_code == ErrorCode.NOT_AVAILABLE.value


def test_emit_log_swallows_hook_errors(caplog: pytest.LogCaptureFixture) -> None:
    received_events: list[ProviderLogEvent] = []

    def failing_hook(event: ProviderLogEvent) -> None:
        del event
        raise RuntimeError("hook failed")

    def collecting_hook(event: ProviderLogEvent) -> None:
        received_events.append(event)

    client = OmniWeatherClient(
        OmniWeatherConfig(providers=[]),
        log_hooks=[failing_hook, collecting_hook],
    )
    event = ProviderLogEvent(
        provider=ProviderId.OPEN_METEO,
        phase="start",
        message="Fetching forecast",
    )

    with caplog.at_level("ERROR", logger="omni_weather_forecast_apis"):
        client._emit_log(event)

    assert received_events == [event]
    assert "Log hook failed for provider open_meteo (start)" in caplog.text

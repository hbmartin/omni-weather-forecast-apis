from __future__ import annotations

import asyncio

import httpx2
import pytest

from omni_weather_forecast_apis.client import OmniWeatherClient, create_omni_weather
from omni_weather_forecast_apis.plugins import PLUGIN_REGISTRY
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
    RetryPolicy,
)
from tests.helpers import DummyPlugin


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
        client: httpx2.AsyncClient,
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
        client: httpx2.AsyncClient,
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
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        del params, client
        await asyncio.sleep(0.05)
        return PluginFetchSuccess(forecasts=[])


class CapturingTimezoneInstance:
    provider_id = ProviderId.OPEN_METEO

    def __init__(self) -> None:
        self.params: PluginFetchParams | None = None

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(granularity_hourly=True)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        del client
        self.params = params
        return PluginFetchSuccess(forecasts=[])


def test_forecast_returns_partial_results() -> None:
    registry = {
        ProviderId.OPEN_METEO: DummyPlugin(ProviderId.OPEN_METEO, SuccessInstance()),
        ProviderId.OPENWEATHER: DummyPlugin(ProviderId.OPENWEATHER, ErrorInstance()),
    }
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
        plugins=registry,
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


def test_forecast_propagates_request_timezone_to_plugin() -> None:
    instance = CapturingTimezoneInstance()
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                ),
            ],
        ),
        plugins=[DummyPlugin(ProviderId.OPEN_METEO, instance)],
    )

    async def scenario() -> str | None:
        await client.initialize()
        response = await client.forecast(
            ForecastRequest(
                latitude=34.0,
                longitude=-118.0,
                granularity=[Granularity.HOURLY],
                timezone="America/Los_Angeles",
            ),
        )
        await client.close()
        return response.request.timezone

    assert asyncio.run(scenario()) == "America/Los_Angeles"
    assert instance.params is not None
    assert instance.params.timezone == "America/Los_Angeles"


def test_emit_log_feeds_stdlib_logger(caplog: pytest.LogCaptureFixture) -> None:
    registry = {
        ProviderId.OPEN_METEO: DummyPlugin(ProviderId.OPEN_METEO, SuccessInstance()),
        ProviderId.OPENWEATHER: DummyPlugin(ProviderId.OPENWEATHER, ErrorInstance()),
    }
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
        plugins=registry,
    )

    async def scenario() -> None:
        await client.initialize()
        await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()

    with caplog.at_level("DEBUG", logger="omni_weather_forecast_apis"):
        asyncio.run(scenario())

    records = [
        (record.levelname, record.getMessage())
        for record in caplog.records
        if record.name == "omni_weather_forecast_apis"
    ]
    assert ("DEBUG", "[open_meteo] Fetching forecast from open_meteo") in records
    success_records = [
        message
        for level, message in records
        if level == "INFO" and message.startswith("[open_meteo] Succeeded in")
    ]
    assert success_records
    warning_records = [
        message
        for level, message in records
        if level == "WARNING" and message == "[openweather] bad key"
    ]
    assert warning_records


def test_initialized_client_context_manager_does_not_reinitialize() -> None:
    plugin = DummyPlugin(ProviderId.OPEN_METEO, SuccessInstance())
    config = OmniWeatherConfig(
        providers=[
            ProviderRegistration(
                plugin_id=ProviderId.OPEN_METEO,
                config={"token": "a"},
            ),
        ],
    )

    async def scenario() -> None:
        async with await create_omni_weather(config, plugins=[plugin]):
            pass

    asyncio.run(scenario())

    assert plugin.initialize_calls == 1


def test_forecast_wraps_timeouts() -> None:
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.WEATHERAPI,
                    config={"token": "a"},
                ),
            ],
            default_timeout_ms=1,
            retry=RetryPolicy(max_attempts=1),
        ),
        plugins=[DummyPlugin(ProviderId.WEATHERAPI, SlowInstance())],
    )

    async def scenario() -> str:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        return response.results[0].error.code.value

    error_code = asyncio.run(scenario())

    assert error_code == ErrorCode.TIMEOUT.value


def test_unconfigured_requested_provider_returns_error() -> None:
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={"token": "a"},
                ),
            ],
        ),
        plugins={},
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


def test_plugins_param_accepts_iterable_and_mapping() -> None:
    config = OmniWeatherConfig(
        providers=[
            ProviderRegistration(
                plugin_id=ProviderId.OPEN_METEO, config={"token": "a"}
            ),
        ],
    )

    async def scenario(client: OmniWeatherClient) -> str:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        return response.results[0].status

    iterable_client = OmniWeatherClient(
        config,
        plugins=[DummyPlugin(ProviderId.OPEN_METEO, SuccessInstance())],
    )
    mapping_client = OmniWeatherClient(
        config,
        plugins={
            ProviderId.OPEN_METEO: DummyPlugin(
                ProviderId.OPEN_METEO, SuccessInstance()
            ),
        },
    )

    assert asyncio.run(scenario(iterable_client)) == "success"
    assert asyncio.run(scenario(mapping_client)) == "success"


def test_injected_plugins_do_not_leak_into_global_registry() -> None:
    before = dict(PLUGIN_REGISTRY)
    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={"token": "a"},
                ),
            ],
        ),
        plugins=[DummyPlugin(ProviderId.OPEN_METEO, SuccessInstance())],
    )

    async def scenario() -> None:
        await client.initialize()
        await client.close()

    asyncio.run(scenario())

    assert dict(PLUGIN_REGISTRY) == before


def test_omitted_plugins_falls_back_to_global_registry() -> None:
    client = OmniWeatherClient(OmniWeatherConfig(providers=[]))

    async def scenario() -> None:
        await client.initialize()
        await client.close()

    asyncio.run(scenario())

    assert client._plugins is None


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

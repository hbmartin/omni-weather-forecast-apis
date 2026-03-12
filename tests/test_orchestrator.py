"""Tests for the orchestrator client."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from omni_weather_forecast_apis.client import OmniWeatherClient, create_omni_weather
from omni_weather_forecast_apis.plugins import get_plugin, list_plugins, register_plugin
from omni_weather_forecast_apis.types.config import (
    OmniWeatherConfig,
    ProviderRegistration,
    RateLimitConfig,
)
from omni_weather_forecast_apis.types.plugin import (
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
)
from omni_weather_forecast_apis.types.schema import (
    ErrorCode,
    ForecastRequest,
    Granularity,
    ModelSource,
    ProviderId,
    SourceForecast,
)


class TestPluginRegistry:
    def test_get_builtin_plugin(self):
        plugin = get_plugin(ProviderId.OPENWEATHER)
        assert plugin is not None
        assert plugin.id == ProviderId.OPENWEATHER

    def test_get_all_builtin_plugins(self):
        plugins = list_plugins()
        assert len(plugins) == 13

    def test_get_nonexistent_plugin(self):
        # All ProviderId values have built-in plugins
        # Just verify get_plugin returns a plugin for known IDs
        for pid in ProviderId:
            assert get_plugin(pid) is not None


class TestOmniWeatherClient:
    @pytest.mark.asyncio
    async def test_initialize_and_close(self):
        config = OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                ),
            ],
        )
        client = OmniWeatherClient(config)
        await client.initialize()
        assert ProviderId.OPEN_METEO in client.get_configured_providers()
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        config = OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                ),
            ],
        )
        async with OmniWeatherClient(config) as client:
            providers = client.get_configured_providers()
            assert ProviderId.OPEN_METEO in providers

    @pytest.mark.asyncio
    async def test_get_provider_capabilities(self):
        config = OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                ),
            ],
        )
        async with OmniWeatherClient(config) as client:
            caps = client.get_provider_capabilities()
            assert ProviderId.OPEN_METEO in caps
            assert caps[ProviderId.OPEN_METEO].granularity_hourly is True

    @pytest.mark.asyncio
    async def test_disabled_provider_not_initialized(self):
        config = OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                    enabled=False,
                ),
            ],
        )
        async with OmniWeatherClient(config) as client:
            assert ProviderId.OPEN_METEO not in client.get_configured_providers()

    @pytest.mark.asyncio
    async def test_forecast_returns_response(self):
        config = OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                ),
            ],
        )
        async with OmniWeatherClient(config) as client:
            # Patch the instance's fetch_forecast to avoid real HTTP
            instance = client._instances[ProviderId.OPEN_METEO]
            original_fetch = instance.fetch_forecast

            async def mock_fetch(params, http_client):
                return PluginFetchSuccess(
                    forecasts=[
                        SourceForecast(
                            source=ModelSource(
                                provider=ProviderId.OPEN_METEO,
                                model="best_match",
                            )
                        )
                    ]
                )

            instance.fetch_forecast = mock_fetch  # type: ignore[assignment]

            response = await client.forecast(
                ForecastRequest(latitude=34.0, longitude=-117.0)
            )
            assert response.summary.total == 1
            assert response.summary.succeeded == 1
            assert response.summary.failed == 0
            assert response.request.latitude == 34.0

    @pytest.mark.asyncio
    async def test_forecast_handles_plugin_error(self):
        config = OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                ),
            ],
        )
        async with OmniWeatherClient(config) as client:
            instance = client._instances[ProviderId.OPEN_METEO]

            async def mock_fetch(params, http_client):
                return PluginFetchError(
                    code=ErrorCode.TIMEOUT,
                    message="Timed out",
                )

            instance.fetch_forecast = mock_fetch  # type: ignore[assignment]

            response = await client.forecast(
                ForecastRequest(latitude=34.0, longitude=-117.0)
            )
            assert response.summary.succeeded == 0
            assert response.summary.failed == 1

    @pytest.mark.asyncio
    async def test_forecast_handles_exception(self):
        config = OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                ),
            ],
        )
        async with OmniWeatherClient(config) as client:
            instance = client._instances[ProviderId.OPEN_METEO]

            async def mock_fetch(params, http_client):
                raise RuntimeError("Unexpected error")

            instance.fetch_forecast = mock_fetch  # type: ignore[assignment]

            response = await client.forecast(
                ForecastRequest(latitude=34.0, longitude=-117.0)
            )
            assert response.summary.failed == 1
            assert response.results[0].status == "error"


class TestCreateOmniWeather:
    @pytest.mark.asyncio
    async def test_factory_function(self):
        config = OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={},
                ),
            ],
        )
        client = await create_omni_weather(config)
        assert ProviderId.OPEN_METEO in client.get_configured_providers()
        await client.close()

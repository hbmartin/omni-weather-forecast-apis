"""Orchestrator client for weather forecast aggregation."""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self

import httpx

from omni_weather_forecast_apis.plugins import get_plugin
from omni_weather_forecast_apis.rate_limiter import TokenBucketRateLimiter
from omni_weather_forecast_apis.types.plugin import (
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
    PluginInstance,
)
from omni_weather_forecast_apis.types.schema import (
    ErrorCode,
    ForecastRequest,
    ForecastResponse,
    ForecastResponseRequest,
    ForecastResponseSummary,
    ProviderError,
    ProviderErrorDetail,
    ProviderId,
    ProviderResult,
    ProviderSuccess,
)

if TYPE_CHECKING:
    from omni_weather_forecast_apis.types.config import OmniWeatherConfig

logger = logging.getLogger("omni_weather_forecast_apis")


class OmniWeatherClient:
    """The main client for fetching forecasts from multiple providers."""

    def __init__(self, config: OmniWeatherConfig) -> None:
        self._config = config
        self._instances: dict[ProviderId, PluginInstance] = {}
        self._http_client: httpx.AsyncClient | None = None
        self._global_semaphore: asyncio.Semaphore | None = None
        self._global_rate_limiter: TokenBucketRateLimiter | None = None
        self._provider_rate_limiters: dict[ProviderId, TokenBucketRateLimiter] = {}

    async def initialize(self) -> None:
        """Validate all provider configs and initialize plugins."""
        self._global_semaphore = asyncio.Semaphore(
            self._config.rate_limiting.max_concurrent,
        )
        self._global_rate_limiter = TokenBucketRateLimiter(
            rate=self._config.rate_limiting.max_requests_per_second,
        )
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._config.default_timeout_ms / 1000.0),
            follow_redirects=True,
        )

        for reg in self._config.providers:
            if not reg.enabled:
                continue
            plugin = get_plugin(reg.plugin_id)
            if plugin is None:
                logger.warning("No plugin found for %s", reg.plugin_id.value)
                continue
            try:
                validated_config = plugin.validate_config(reg.config)
                instance = await plugin.initialize(validated_config)
                self._instances[reg.plugin_id] = instance

                if reg.rate_limit_rps is not None:
                    self._provider_rate_limiters[reg.plugin_id] = (
                        TokenBucketRateLimiter(rate=reg.rate_limit_rps)
                    )
            except Exception:
                logger.exception("Failed to initialize plugin %s", reg.plugin_id.value)

    async def close(self) -> None:
        """Clean up HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def forecast(self, request: ForecastRequest) -> ForecastResponse:
        """Fetch forecasts from all (or selected) configured providers."""
        start = time.perf_counter()

        target_ids = (
            [p for p in request.providers if p in self._instances]
            if request.providers
            else list(self._instances.keys())
        )

        tasks = [
            self._fetch_provider(provider_id, request) for provider_id in target_ids
        ]

        results: list[ProviderResult] = list(
            await asyncio.gather(*tasks, return_exceptions=False),
        )

        succeeded = sum(1 for r in results if r.status == "success")
        failed = len(results) - succeeded
        elapsed_ms = (time.perf_counter() - start) * 1000

        return ForecastResponse(
            request=ForecastResponseRequest(
                latitude=request.latitude,
                longitude=request.longitude,
                granularity=request.granularity,
            ),
            results=results,
            summary=ForecastResponseSummary(
                total=len(results),
                succeeded=succeeded,
                failed=failed,
            ),
            completed_at=datetime.now(UTC),
            total_latency_ms=elapsed_ms,
        )

    def get_provider_capabilities(self) -> dict[ProviderId, PluginCapabilities]:
        """Get capabilities for all configured providers."""
        return {
            pid: instance.get_capabilities()
            for pid, instance in self._instances.items()
        }

    def get_configured_providers(self) -> list[ProviderId]:
        """Check which providers are configured and enabled."""
        return list(self._instances.keys())

    async def _fetch_provider(
        self,
        provider_id: ProviderId,
        request: ForecastRequest,
    ) -> ProviderResult:
        """Fetch from a single provider with rate limiting and error handling."""
        start = time.perf_counter()
        instance = self._instances[provider_id]

        try:
            if (
                self._global_semaphore is None
                or self._global_rate_limiter is None
                or self._http_client is None
            ):
                msg = "Client not initialized. Call initialize() first."
                raise RuntimeError(msg)  # noqa: TRY301

            async with self._global_semaphore:
                await self._global_rate_limiter.acquire()

                if provider_limiter := self._provider_rate_limiters.get(provider_id):
                    await provider_limiter.acquire()

                timeout_ms = self._get_timeout(provider_id, request)
                self._http_client.timeout = httpx.Timeout(timeout_ms / 1000.0)
                client = self._http_client

                params = PluginFetchParams(
                    latitude=request.latitude,
                    longitude=request.longitude,
                    granularity=request.granularity,
                    include_raw=request.include_raw,
                )

                logger.info("Fetching forecast from %s", provider_id.value)
                result = await instance.fetch_forecast(params, client)
                latency_ms = (time.perf_counter() - start) * 1000

                match result:
                    case PluginFetchSuccess():
                        logger.info(
                            "Provider %s succeeded in %.0fms",
                            provider_id.value,
                            latency_ms,
                        )
                        return ProviderSuccess(
                            provider=provider_id,
                            forecasts=result.forecasts,
                            fetched_at=datetime.now(UTC),
                            latency_ms=latency_ms,
                            raw=result.raw,
                        )
                    case PluginFetchError():
                        logger.warning(
                            "Provider %s failed: %s",
                            provider_id.value,
                            result.message,
                        )
                        return ProviderError(
                            provider=provider_id,
                            error=ProviderErrorDetail(
                                code=result.code,
                                message=result.message,
                                http_status=result.http_status,
                                latency_ms=latency_ms,
                                raw=result.raw,
                            ),
                        )

        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "Provider %s raised unexpected exception",
                provider_id.value,
            )
            return ProviderError(
                provider=provider_id,
                error=ProviderErrorDetail(
                    code=ErrorCode.UNKNOWN,
                    message=str(exc),
                    latency_ms=latency_ms,
                ),
            )

        latency_ms = (time.perf_counter() - start) * 1000
        return ProviderError(
            provider=provider_id,
            error=ProviderErrorDetail(
                code=ErrorCode.UNKNOWN,
                message="Unexpected result type from plugin",
                latency_ms=latency_ms,
            ),
        )

    def _get_timeout(self, provider_id: ProviderId, request: ForecastRequest) -> float:
        """Get the effective timeout for a provider."""
        for reg in self._config.providers:
            if reg.plugin_id == provider_id and reg.timeout_ms is not None:
                return reg.timeout_ms
        return request.timeout_ms


async def create_omni_weather(
    config: OmniWeatherConfig,
) -> OmniWeatherClient:
    """Create and initialize an OmniWeatherClient."""
    client = OmniWeatherClient(config)
    await client.initialize()
    return client

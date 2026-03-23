from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from omni_weather_forecast_apis.plugins import get_plugin_registry
from omni_weather_forecast_apis.rate_limiter import (
    CompositeRateLimiter,
    TokenBucketRateLimiter,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ForecastRequest,
    ForecastResponse,
    ForecastResponseRequest,
    ForecastResponseSummary,
    Granularity,
    LogHook,
    OmniWeatherConfig,
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginInstance,
    ProviderError,
    ProviderErrorDetail,
    ProviderId,
    ProviderLogEvent,
    ProviderRegistration,
    ProviderResult,
    ProviderSuccess,
)
from omni_weather_forecast_apis.utils import utc_now

logger = logging.getLogger("omni_weather_forecast_apis")


class OmniWeatherClient:
    """Main async aggregation client."""

    def __init__(
        self,
        config: OmniWeatherConfig,
        *,
        log_hooks: list[LogHook] | None = None,
    ) -> None:
        self._config = config
        self._log_hooks: list[LogHook] = log_hooks or []
        self._instances: dict[ProviderId, PluginInstance] = {}
        self._provider_registrations: dict[ProviderId, ProviderRegistration] = {}
        self._initialization_errors: dict[ProviderId, str] = {}
        self._http_client: httpx.AsyncClient | None = None
        self._global_rate_limiter = TokenBucketRateLimiter(
            config.rate_limiting.max_requests_per_second,
        )
        self._concurrency_limiter = asyncio.Semaphore(
            config.rate_limiting.max_in_flight,
        )
        self._provider_limiters: dict[ProviderId, TokenBucketRateLimiter] = {}

    async def initialize(self) -> None:
        """Validate provider configs and initialize provider instances."""

        registry = get_plugin_registry()
        self._instances.clear()
        self._provider_registrations = {
            registration.plugin_id: registration
            for registration in self._config.providers
            if registration.enabled
        }
        self._initialization_errors.clear()
        self._provider_limiters.clear()

        for registration in self._config.providers:
            if not registration.enabled:
                continue
            plugin = registry.get(registration.plugin_id)
            if plugin is None:
                self._initialization_errors[registration.plugin_id] = (
                    "Provider plugin is not registered."
                )
                continue
            try:
                validated_config = plugin.validate_config(registration.config)
                instance = await plugin.initialize(validated_config)
            except Exception as exc:
                self._initialization_errors[registration.plugin_id] = (
                    f"Failed to initialize provider: {exc}"
                )
                continue
            self._instances[registration.plugin_id] = instance
            if registration.rate_limit_rps is not None:
                self._provider_limiters[registration.plugin_id] = (
                    TokenBucketRateLimiter(
                        registration.rate_limit_rps,
                    )
                )

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=None,
            )

    async def close(self) -> None:
        """Close HTTP resources."""

        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> OmniWeatherClient:
        await self.initialize()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def forecast(self, request: ForecastRequest) -> ForecastResponse:
        """Fetch forecasts from the selected providers."""

        if self._http_client is None:
            await self.initialize()
        client = self._http_client
        if client is None:
            raise RuntimeError("HTTP client initialization failed unexpectedly.")

        started_at = time.perf_counter()
        target_providers = self._resolve_target_providers(request)
        tasks = [
            self._fetch_one_provider(provider_id, request, client)
            for provider_id in target_providers
        ]
        results = await asyncio.gather(*tasks)
        completed_at = utc_now()
        succeeded = sum(isinstance(item, ProviderSuccess) for item in results)
        failed = len(results) - succeeded
        return ForecastResponse(
            request=ForecastResponseRequest(
                latitude=request.latitude,
                longitude=request.longitude,
                granularity=request.granularity,
                language=request.language,
            ),
            results=results,
            summary=ForecastResponseSummary(
                total=len(results),
                succeeded=succeeded,
                failed=failed,
            ),
            completed_at=completed_at,
            total_latency_ms=(time.perf_counter() - started_at) * 1000,
        )

    def get_provider_capabilities(self) -> dict[ProviderId, PluginCapabilities]:
        """Return capabilities for initialized providers."""

        return {
            provider_id: instance.get_capabilities()
            for provider_id, instance in self._instances.items()
        }

    def get_configured_providers(self) -> list[ProviderId]:
        """Return enabled configured providers."""

        return [
            registration.plugin_id
            for registration in self._config.providers
            if registration.enabled
        ]

    def _emit_log(self, event: ProviderLogEvent) -> None:
        for hook in self._log_hooks:
            try:
                hook(event)
            except (Exception,):  # noqa: B013
                logger.exception(
                    "Log hook failed for provider %s (%s)",
                    event.provider.value,
                    event.phase,
                )

    async def _fetch_one_provider(
        self,
        provider_id: ProviderId,
        request: ForecastRequest,
        client: httpx.AsyncClient,
    ) -> ProviderResult:
        started_at = time.perf_counter()
        registration = self._provider_registrations.get(provider_id)
        if registration is None:
            return self._provider_error(
                provider_id,
                ErrorCode.NOT_AVAILABLE,
                "Provider is not configured or is disabled.",
                started_at,
            )

        if (init_error := self._initialization_errors.get(provider_id)) is not None:
            return self._provider_error(
                provider_id,
                ErrorCode.NOT_AVAILABLE,
                init_error,
                started_at,
            )

        instance = self._instances.get(provider_id)
        if instance is None:
            return self._provider_error(
                provider_id,
                ErrorCode.NOT_AVAILABLE,
                "Provider instance is unavailable.",
                started_at,
            )

        capabilities = instance.get_capabilities()
        supported_granularity = _filter_supported_granularity(
            request.granularity,
            capabilities,
        )
        if not supported_granularity:
            return self._provider_error(
                provider_id,
                ErrorCode.NOT_AVAILABLE,
                "Requested granularities are not supported by this provider.",
                started_at,
            )

        self._emit_log(ProviderLogEvent(
            provider=provider_id,
            phase="start",
            message=f"Fetching forecast from {provider_id.value}",
        ))
        params = PluginFetchParams(
            latitude=request.latitude,
            longitude=request.longitude,
            granularity=supported_granularity,
            language=request.language,
            include_raw=request.include_raw,
        )
        timeout_ms = _resolve_timeout_ms(
            self._config.default_timeout_ms,
            registration.timeout_ms,
            request,
        )
        limiter = CompositeRateLimiter(
            self._concurrency_limiter,
            self._global_rate_limiter,
            self._provider_limiters.get(provider_id),
        )
        try:
            async with limiter.slot():
                async with asyncio.timeout(timeout_ms / 1000):
                    result = await instance.fetch_forecast(params, client)
        except TimeoutError:
            latency_ms = (time.perf_counter() - started_at) * 1000
            self._emit_log(ProviderLogEvent(
                provider=provider_id,
                phase="error",
                message=f"Request exceeded timeout of {timeout_ms} ms.",
                latency_ms=latency_ms,
                error_code=ErrorCode.TIMEOUT,
            ))
            return self._provider_error(
                provider_id,
                ErrorCode.TIMEOUT,
                f"Request exceeded timeout of {timeout_ms} ms.",
                started_at,
            )
        except httpx.HTTPError as exc:
            latency_ms = (time.perf_counter() - started_at) * 1000
            self._emit_log(ProviderLogEvent(
                provider=provider_id,
                phase="error",
                message=str(exc),
                latency_ms=latency_ms,
                error_code=ErrorCode.NETWORK,
            ))
            return self._provider_error(
                provider_id,
                ErrorCode.NETWORK,
                str(exc),
                started_at,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started_at) * 1000
            error_code = _exception_error_code(exc)
            self._emit_log(ProviderLogEvent(
                provider=provider_id,
                phase="error",
                message=str(exc),
                latency_ms=latency_ms,
                error_code=error_code,
            ))
            return self._provider_error(
                provider_id,
                error_code,
                str(exc),
                started_at,
            )

        latency_ms = (time.perf_counter() - started_at) * 1000
        match result:
            case PluginFetchError():
                logger.warning(
                    "Provider %s returned error: %s",
                    provider_id.value,
                    result.message,
                )
                self._emit_log(ProviderLogEvent(
                    provider=provider_id,
                    phase="error",
                    message=result.message,
                    latency_ms=latency_ms,
                    error_code=result.code,
                    http_status=result.http_status,
                ))
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
            case _:
                logger.info(
                    "Provider %s succeeded in %.0fms",
                    provider_id.value,
                    latency_ms,
                )
                self._emit_log(ProviderLogEvent(
                    provider=provider_id,
                    phase="success",
                    message=f"Succeeded in {latency_ms:.0f}ms",
                    latency_ms=latency_ms,
                ))
                return ProviderSuccess(
                    provider=provider_id,
                    forecasts=result.forecasts,
                    fetched_at=utc_now(),
                    latency_ms=latency_ms,
                    raw=result.raw if request.include_raw else None,
                )

    def _resolve_target_providers(self, request: ForecastRequest) -> list[ProviderId]:
        if request.providers is None:
            return self.get_configured_providers()

        ordered_unique: list[ProviderId] = []
        seen: set[ProviderId] = set()
        for provider in request.providers:
            if provider not in seen:
                seen.add(provider)
                ordered_unique.append(provider)
        return ordered_unique

    def _provider_error(
        self,
        provider_id: ProviderId,
        code: ErrorCode,
        message: str,
        started_at: float,
        *,
        http_status: int | None = None,
        raw: Any | None = None,
    ) -> ProviderError:
        return ProviderError(
            provider=provider_id,
            error=ProviderErrorDetail(
                code=code,
                message=message,
                http_status=http_status,
                latency_ms=(time.perf_counter() - started_at) * 1000,
                raw=raw,
            ),
        )


async def create_omni_weather(
    config: OmniWeatherConfig,
    *,
    log_hooks: list[LogHook] | None = None,
) -> OmniWeatherClient:
    """Create and initialize an OmniWeather client."""

    client = OmniWeatherClient(config, log_hooks=log_hooks)
    await client.initialize()
    return client


def _filter_supported_granularity(
    requested: list[Granularity],
    capabilities: PluginCapabilities,
) -> list[Granularity]:
    supported: list[Granularity] = []
    for granularity in requested:
        match granularity:
            case Granularity.MINUTELY if capabilities.granularity_minutely:
                supported.append(granularity)
            case Granularity.HOURLY if capabilities.granularity_hourly:
                supported.append(granularity)
            case Granularity.DAILY if capabilities.granularity_daily:
                supported.append(granularity)
            case _:
                continue
    return supported


def _resolve_timeout_ms(
    default_timeout_ms: float,
    provider_timeout_ms: float | None,
    request: ForecastRequest,
) -> float:
    if provider_timeout_ms is not None:
        return provider_timeout_ms
    if request.timeout_ms is not None:
        return request.timeout_ms
    return default_timeout_ms


def _exception_error_code(exc: Exception) -> ErrorCode:
    match exc:
        case httpx.TimeoutException():
            return ErrorCode.TIMEOUT
        case httpx.NetworkError():
            return ErrorCode.NETWORK
        case ValueError():
            return ErrorCode.PARSE
        case _:
            return ErrorCode.UNKNOWN

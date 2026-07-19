from __future__ import annotations

import asyncio
import inspect
import logging
import random
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

import httpx2

from omni_weather_forecast_apis.http_cache import CachingTransport
from omni_weather_forecast_apis.http_recorder import RawArchiveTransport
from omni_weather_forecast_apis.plugins import get_plugin_registry
from omni_weather_forecast_apis.quota import InMemoryQuotaTracker, QuotaTracker
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
    MetricEvent,
    MetricKind,
    MetricsHook,
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
    ResponseHook,
    RetryPolicy,
    WeatherPlugin,
)
from omni_weather_forecast_apis.utils import (
    resolve_env_placeholders,
    utc_now,
    zoneinfo_from_name,
)

logger = logging.getLogger("omni_weather_forecast_apis")

type PluginsInput = Mapping[ProviderId, WeatherPlugin] | Iterable[WeatherPlugin]


@dataclass
class _RequestStats:
    """Mutable per-forecast() counters shared across provider tasks."""

    retries: int = 0


def _normalize_plugins(
    plugins: PluginsInput | None,
) -> dict[ProviderId, WeatherPlugin] | None:
    match plugins:
        case None:
            return None
        case Mapping():
            mapping = cast("Mapping[ProviderId, WeatherPlugin]", plugins)
            return dict(mapping)
        case _:
            return {plugin.id: plugin for plugin in plugins}


_PHASE_LOG_LEVELS: dict[str, int] = {
    "start": logging.DEBUG,
    "retry": logging.INFO,
    "success": logging.INFO,
    "error": logging.WARNING,
}
_RETRYABLE_ERROR_CODES: frozenset[ErrorCode] = frozenset(
    {ErrorCode.NETWORK, ErrorCode.TIMEOUT, ErrorCode.RATE_LIMITED},
)
_MAX_HONORED_RETRY_AFTER_SECONDS = 60.0
_TIMEZONE_LOOKUP_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEZONE_LOOKUP_TIMEOUT_SECONDS: float = 10.0


class OmniWeatherClient:
    """Main async aggregation client."""

    def __init__(
        self,
        config: OmniWeatherConfig,
        *,
        plugins: PluginsInput | None = None,
        log_hooks: list[LogHook] | None = None,
        response_hooks: list[ResponseHook] | None = None,
        metrics_hooks: list[MetricsHook] | None = None,
        quota_tracker: QuotaTracker | None = None,
    ) -> None:
        self._config = config
        self._plugins = _normalize_plugins(plugins)
        self._log_hooks: list[LogHook] = log_hooks or []
        self._metrics_hooks: list[MetricsHook] = metrics_hooks or []
        self._response_hooks: list[ResponseHook] = response_hooks or []
        self._quota_tracker: QuotaTracker = quota_tracker or InMemoryQuotaTracker()
        self._instances: dict[ProviderId, PluginInstance] = {}
        self._provider_registrations: dict[ProviderId, ProviderRegistration] = {}
        self._initialization_errors: dict[ProviderId, str] = {}
        self._http_client: httpx2.AsyncClient | None = None
        self._global_rate_limiter = TokenBucketRateLimiter(
            config.rate_limiting.max_requests_per_second,
        )
        self._concurrency_limiter = asyncio.Semaphore(
            config.rate_limiting.max_in_flight,
        )
        self._provider_limiters: dict[ProviderId, TokenBucketRateLimiter] = {}

    async def initialize(self) -> None:
        """Validate provider configs and initialize provider instances."""

        registry = self._plugins if self._plugins is not None else get_plugin_registry()
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
                resolved_config = resolve_env_placeholders(registration.config)
                validated_config = plugin.validate_config(resolved_config)
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
            self._http_client = self._build_http_client()

    def _build_http_client(self) -> httpx2.AsyncClient:
        http_config = self._config.http
        transport: httpx2.AsyncBaseTransport = httpx2.AsyncHTTPTransport(
            limits=httpx2.Limits(
                max_connections=http_config.max_connections,
                max_keepalive_connections=http_config.max_keepalive_connections,
            ),
        )
        # The recorder sits inside the cache so cache hits are not recorded.
        if http_config.raw_archive_enabled and http_config.raw_archive_path:
            transport = RawArchiveTransport(transport, http_config.raw_archive_path)
        if http_config.cache_enabled:
            transport = CachingTransport(
                transport,
                max_entries=http_config.cache_max_entries,
                on_cache_event=self._handle_cache_event,
            )
        return httpx2.AsyncClient(
            follow_redirects=True,
            timeout=httpx2.Timeout(
                None,
                connect=http_config.connect_timeout_ms / 1000,
            ),
            transport=transport,
        )

    async def close(self) -> None:
        """Close HTTP resources."""

        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def lookup_location_timezone(
        self,
        latitude: float,
        longitude: float,
    ) -> str:
        """Resolve an IANA zone through the client's configured HTTP transport."""

        if self._http_client is None:
            await self.initialize()
        client = self._http_client
        if client is None:
            raise RuntimeError("HTTP client initialization failed unexpectedly.")
        response = await client.get(
            _TIMEZONE_LOOKUP_URL,
            timeout=_TIMEZONE_LOOKUP_TIMEOUT_SECONDS,
            params={
                "latitude": f"{latitude:.6f}",
                "longitude": f"{longitude:.6f}",
                "timezone": "auto",
                "forecast_days": 1,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("timezone response is not a JSON object")
        if (location_timezone := zoneinfo_from_name(payload.get("timezone"))) is None:
            raise ValueError("timezone response lacks a valid IANA timezone")
        return location_timezone.key

    async def __aenter__(self) -> OmniWeatherClient:
        if self._http_client is None:
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
        stats = _RequestStats()
        target_providers = self._resolve_target_providers(request)
        tasks = [
            self._fetch_one_provider(provider_id, request, client, stats)
            for provider_id in target_providers
        ]
        results = await asyncio.gather(*tasks)
        completed_at = utc_now()
        succeeded = sum(isinstance(item, ProviderSuccess) for item in results)
        failed = len(results) - succeeded
        response = ForecastResponse(
            request=ForecastResponseRequest(
                latitude=request.latitude,
                longitude=request.longitude,
                granularity=request.granularity,
                language=request.language,
                timezone=request.timezone,
            ),
            results=results,
            summary=ForecastResponseSummary(
                total=len(results),
                succeeded=succeeded,
                failed=failed,
                retries=stats.retries,
            ),
            completed_at=completed_at,
            total_latency_ms=(time.perf_counter() - started_at) * 1000,
        )
        await self._run_response_hooks(response)
        return response

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
        logger.log(
            _PHASE_LOG_LEVELS[event.phase],
            "[%s] %s",
            event.provider.value,
            event.message,
        )
        for hook in self._log_hooks:
            try:
                hook(event)
            except (Exception,):
                logger.exception(
                    "Log hook failed for provider %s (%s)",
                    event.provider.value,
                    event.phase,
                )

    def _emit_metric(self, event: MetricEvent) -> None:
        for hook in self._metrics_hooks:
            try:
                hook(event)
            except (Exception,):
                logger.exception("Metrics hook failed (%s)", event.kind.value)

    def _handle_cache_event(self, url: str, outcome: str) -> None:
        kind = (
            MetricKind.CACHE_HIT
            if outcome in {"hit", "revalidated"}
            else MetricKind.CACHE_MISS
        )
        self._emit_metric(
            MetricEvent(
                kind=kind,
                url=url,
                extra={"outcome": outcome},
            )
        )

    async def _run_response_hooks(self, response: ForecastResponse) -> None:
        for hook in self._response_hooks:
            try:
                result = hook(response)
                if inspect.isawaitable(result):
                    await result
            except (Exception,):
                logger.exception("Response hook failed")

    async def _fetch_one_provider(
        self,
        provider_id: ProviderId,
        request: ForecastRequest,
        client: httpx2.AsyncClient,
        stats: _RequestStats,
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

        self._emit_log(
            ProviderLogEvent(
                provider=provider_id,
                phase="start",
                message=f"Fetching forecast from {provider_id.value}",
            )
        )
        params = PluginFetchParams(
            latitude=request.latitude,
            longitude=request.longitude,
            granularity=supported_granularity,
            language=request.language,
            timezone=request.timezone,
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
        policy = registration.retry or self._config.retry

        attempt = 1
        while True:
            quota_error = await self._quota_error_or_record(
                provider_id,
                registration,
                started_at,
            )
            if quota_error is not None:
                return quota_error

            result, retry_after_seconds = await self._attempt_fetch(
                provider_id,
                instance,
                params,
                client,
                limiter,
                timeout_ms,
                started_at,
                request,
                attempt,
            )
            if isinstance(result, ProviderSuccess):
                return result
            if (
                attempt >= policy.max_attempts
                or result.error.code not in _RETRYABLE_ERROR_CODES
            ):
                return result
            delay_seconds = _compute_backoff_seconds(
                policy,
                attempt,
                retry_after_seconds,
            )
            if delay_seconds is None:
                return result
            stats.retries += 1
            self._emit_metric(
                MetricEvent(
                    kind=MetricKind.RETRY_SCHEDULED,
                    provider=provider_id,
                    attempt=attempt,
                    error_code=result.error.code,
                    http_status=result.error.http_status,
                    extra={"delay_seconds": delay_seconds},
                )
            )
            self._emit_log(
                ProviderLogEvent(
                    provider=provider_id,
                    phase="retry",
                    message=(
                        f"Attempt {attempt}/{policy.max_attempts} failed with "
                        f"{result.error.code.value}; retrying in {delay_seconds:.1f}s"
                    ),
                    latency_ms=(time.perf_counter() - started_at) * 1000,
                    error_code=result.error.code,
                    http_status=result.error.http_status,
                    extra={"attempt": attempt, "delay_seconds": delay_seconds},
                )
            )
            await asyncio.sleep(delay_seconds)
            attempt += 1

    async def _attempt_fetch(
        self,
        provider_id: ProviderId,
        instance: PluginInstance,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
        limiter: CompositeRateLimiter,
        timeout_ms: float,
        started_at: float,
        request: ForecastRequest,
        attempt: int,
    ) -> tuple[ProviderResult, float | None]:
        attempt_started = time.perf_counter()
        self._emit_metric(
            MetricEvent(
                kind=MetricKind.REQUEST_START,
                provider=provider_id,
                attempt=attempt,
            )
        )

        def _attempt_latency_ms() -> float:
            return (time.perf_counter() - attempt_started) * 1000

        def _end_metric(
            error_code: ErrorCode | None,
            http_status: int | None = None,
        ) -> None:
            self._emit_metric(
                MetricEvent(
                    kind=MetricKind.REQUEST_END,
                    provider=provider_id,
                    attempt=attempt,
                    latency_ms=_attempt_latency_ms(),
                    error_code=error_code,
                    http_status=http_status,
                )
            )

        try:
            async with limiter.slot():
                async with asyncio.timeout(timeout_ms / 1000):
                    result = await instance.fetch_forecast(params, client)
        except TimeoutError:
            latency_ms = (time.perf_counter() - started_at) * 1000
            _end_metric(ErrorCode.TIMEOUT)
            self._emit_log(
                ProviderLogEvent(
                    provider=provider_id,
                    phase="error",
                    message=f"Request exceeded timeout of {timeout_ms} ms.",
                    latency_ms=latency_ms,
                    error_code=ErrorCode.TIMEOUT,
                )
            )
            return self._provider_error(
                provider_id,
                ErrorCode.TIMEOUT,
                f"Request exceeded timeout of {timeout_ms} ms.",
                started_at,
            ), None
        except httpx2.HTTPError as exc:
            latency_ms = (time.perf_counter() - started_at) * 1000
            _end_metric(ErrorCode.NETWORK)
            self._emit_log(
                ProviderLogEvent(
                    provider=provider_id,
                    phase="error",
                    message=str(exc),
                    latency_ms=latency_ms,
                    error_code=ErrorCode.NETWORK,
                )
            )
            return self._provider_error(
                provider_id,
                ErrorCode.NETWORK,
                str(exc),
                started_at,
            ), None
        except Exception as exc:
            latency_ms = (time.perf_counter() - started_at) * 1000
            error_code = _exception_error_code(exc)
            _end_metric(error_code)
            self._emit_log(
                ProviderLogEvent(
                    provider=provider_id,
                    phase="error",
                    message=str(exc),
                    latency_ms=latency_ms,
                    error_code=error_code,
                )
            )
            return self._provider_error(
                provider_id,
                error_code,
                str(exc),
                started_at,
            ), None

        latency_ms = (time.perf_counter() - started_at) * 1000
        match result:
            case PluginFetchError():
                _end_metric(result.code, result.http_status)
                self._emit_log(
                    ProviderLogEvent(
                        provider=provider_id,
                        phase="error",
                        message=result.message,
                        latency_ms=latency_ms,
                        error_code=result.code,
                        http_status=result.http_status,
                    )
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
                ), result.retry_after_seconds
            case _:
                _end_metric(None)
                self._emit_log(
                    ProviderLogEvent(
                        provider=provider_id,
                        phase="success",
                        message=f"Succeeded in {latency_ms:.0f}ms",
                        latency_ms=latency_ms,
                    )
                )
                return ProviderSuccess(
                    provider=provider_id,
                    forecasts=result.forecasts,
                    fetched_at=utc_now(),
                    latency_ms=latency_ms,
                    raw=result.raw if request.include_raw else None,
                ), None

    async def _quota_error_or_record(
        self,
        provider_id: ProviderId,
        registration: ProviderRegistration,
        started_at: float,
    ) -> ProviderError | None:
        limit = registration.max_requests_per_day
        if limit is None:
            return None
        today = utc_now().date()
        try:
            consumed = await asyncio.to_thread(
                self._quota_tracker.try_consume,
                provider_id,
                today,
                limit,
            )
        except (Exception,) as exc:
            message = f"Quota tracking failed: {exc}"
            self._emit_log(
                ProviderLogEvent(
                    provider=provider_id,
                    phase="error",
                    message=message,
                    latency_ms=(time.perf_counter() - started_at) * 1000,
                    error_code=ErrorCode.UNKNOWN,
                )
            )
            return self._provider_error(
                provider_id,
                ErrorCode.UNKNOWN,
                message,
                started_at,
            )
        if consumed:
            self._emit_metric(
                MetricEvent(
                    kind=MetricKind.QUOTA_CONSUMED,
                    provider=provider_id,
                    extra={"limit": limit},
                )
            )
        else:
            self._emit_metric(
                MetricEvent(
                    kind=MetricKind.QUOTA_EXHAUSTED,
                    provider=provider_id,
                    error_code=ErrorCode.QUOTA_EXCEEDED,
                    extra={"limit": limit},
                )
            )
        if not consumed:
            message = (
                f"Daily quota of {limit} requests is exhausted for {today.isoformat()}."
            )
            self._emit_log(
                ProviderLogEvent(
                    provider=provider_id,
                    phase="error",
                    message=message,
                    latency_ms=(time.perf_counter() - started_at) * 1000,
                    error_code=ErrorCode.QUOTA_EXCEEDED,
                )
            )
            return self._provider_error(
                provider_id,
                ErrorCode.QUOTA_EXCEEDED,
                message,
                started_at,
            )
        return None

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
    plugins: PluginsInput | None = None,
    log_hooks: list[LogHook] | None = None,
    response_hooks: list[ResponseHook] | None = None,
    metrics_hooks: list[MetricsHook] | None = None,
    quota_tracker: QuotaTracker | None = None,
) -> OmniWeatherClient:
    """Create and initialize an OmniWeather client.

    ``plugins`` scopes the plugin set to this client instance — pass a
    sequence of plugins or a mapping keyed by provider id. When omitted,
    the client falls back to the process-global registry.

    ``metrics_hooks`` receive a MetricEvent for every request attempt,
    retry, cache hit/miss, and quota consumption.
    """

    client = OmniWeatherClient(
        config,
        plugins=plugins,
        log_hooks=log_hooks,
        response_hooks=response_hooks,
        metrics_hooks=metrics_hooks,
        quota_tracker=quota_tracker,
    )
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


def _compute_backoff_seconds(
    policy: RetryPolicy,
    attempt: int,
    retry_after_seconds: float | None,
) -> float | None:
    """Return the delay before the next attempt, or None to give up.

    Honors a server-provided Retry-After unless it is too far in the
    future to be worth waiting for within one aggregation request.
    """

    backoff_seconds = (
        min(
            policy.initial_backoff_ms * policy.backoff_multiplier ** (attempt - 1),
            policy.max_backoff_ms,
        )
        / 1000
    )
    if policy.jitter:
        backoff_seconds *= 0.5 + random.random() / 2  # noqa: S311
    if retry_after_seconds is not None:
        if retry_after_seconds > _MAX_HONORED_RETRY_AFTER_SECONDS:
            return None
        backoff_seconds = max(backoff_seconds, retry_after_seconds)
    return backoff_seconds


def _exception_error_code(exc: Exception) -> ErrorCode:
    match exc:
        case httpx2.TimeoutException():
            return ErrorCode.TIMEOUT
        case httpx2.NetworkError():
            return ErrorCode.NETWORK
        case ValueError():
            return ErrorCode.PARSE
        case _:
            return ErrorCode.UNKNOWN

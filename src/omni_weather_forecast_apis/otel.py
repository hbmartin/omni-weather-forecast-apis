"""Optional OpenTelemetry bridge for MetricsHook events.

Requires the ``otel`` extra::

    pip install "omni-weather-forecast-apis[otel]"
"""

from __future__ import annotations

from typing import Any

from omni_weather_forecast_apis.types import MetricEvent, MetricKind, MetricsHook


def create_otel_metrics_hook(meter_provider: Any | None = None) -> MetricsHook:
    """Build a MetricsHook that records events as OpenTelemetry metrics.

    Instruments created (all under the ``omni_weather`` prefix):

    - ``omni_weather.requests`` (counter; attrs: provider, outcome)
    - ``omni_weather.request.duration_ms`` (histogram; attrs: provider)
    - ``omni_weather.retries`` (counter; attrs: provider, error_code)
    - ``omni_weather.cache`` (counter; attrs: outcome)
    - ``omni_weather.quota.consumed`` (counter; attrs: provider)
    - ``omni_weather.quota.exhausted`` (counter; attrs: provider)

    ``meter_provider`` defaults to the globally configured provider.
    """

    try:
        from opentelemetry import (  # noqa: PLC0415  # pyrefly: ignore[missing-import]
            metrics as otel_metrics,
        )
    except ImportError as exc:
        raise ImportError(
            "OpenTelemetry is not installed; install the otel extra: "
            'pip install "omni-weather-forecast-apis[otel]"',
        ) from exc

    meter = otel_metrics.get_meter(
        "omni_weather_forecast_apis",
        meter_provider=meter_provider,
    )
    requests = meter.create_counter(
        "omni_weather.requests",
        description="Provider fetch attempts, by outcome",
    )
    duration = meter.create_histogram(
        "omni_weather.request.duration_ms",
        unit="ms",
        description="Per-attempt provider fetch duration",
    )
    retries = meter.create_counter(
        "omni_weather.retries",
        description="Retry attempts scheduled after transient failures",
    )
    cache = meter.create_counter(
        "omni_weather.cache",
        description="HTTP cache lookups, by outcome",
    )
    quota_consumed = meter.create_counter(
        "omni_weather.quota.consumed",
        description="Daily quota units consumed",
    )
    quota_exhausted = meter.create_counter(
        "omni_weather.quota.exhausted",
        description="Requests rejected because the daily quota was spent",
    )

    def _provider_attrs(event: MetricEvent) -> dict[str, str]:
        return {"provider": event.provider.value} if event.provider else {}

    def hook(event: MetricEvent) -> None:
        match event.kind:
            case MetricKind.REQUEST_END:
                outcome = event.error_code.value if event.error_code else "success"
                requests.add(1, {**_provider_attrs(event), "outcome": outcome})
                if event.latency_ms is not None:
                    duration.record(event.latency_ms, _provider_attrs(event))
            case MetricKind.RETRY_SCHEDULED:
                retries.add(
                    1,
                    {
                        **_provider_attrs(event),
                        "error_code": (
                            event.error_code.value if event.error_code else "unknown"
                        ),
                    },
                )
            case MetricKind.CACHE_HIT | MetricKind.CACHE_MISS:
                cache.add(1, {"outcome": str(event.extra.get("outcome", ""))})
            case MetricKind.QUOTA_CONSUMED:
                quota_consumed.add(1, _provider_attrs(event))
            case MetricKind.QUOTA_EXHAUSTED:
                quota_exhausted.add(1, _provider_attrs(event))
            case MetricKind.REQUEST_START:
                pass

    return hook


__all__ = ["create_otel_metrics_hook"]

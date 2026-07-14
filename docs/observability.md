# Observability

The client exposes two hook families. **Log hooks** (`log_hooks`) receive
structured per-provider lifecycle events — `start`, `retry`, `success`,
`error` — the same events the CLI persists to the `provider_logs` table (see
[Database Design](database.md#provider_logs)). **Metrics hooks**
(`metrics_hooks`) receive a typed `MetricEvent` for every request attempt,
retry, HTTP cache lookup, and quota consumption.

Neither needs an extra dependency, and a hook that raises is logged and never
breaks the forecast.

## Metrics hooks

Register any callable that accepts a `MetricEvent`:

```python
from omni_weather_forecast_apis import MetricEvent, MetricKind, create_omni_weather

def record(event: MetricEvent) -> None:
    if event.kind is MetricKind.REQUEST_END:
        print(event.provider, event.latency_ms, event.error_code)

client = await create_omni_weather(config, metrics_hooks=[record])
```

`MetricKind` has seven members:

| Kind | Emitted when |
|------|--------------|
| `request_start` | A provider fetch attempt begins |
| `request_end` | A provider fetch attempt finishes, successfully or not |
| `retry_scheduled` | A transient failure is about to be retried after backoff |
| `cache_hit` | The shared HTTP cache served a response |
| `cache_miss` | The shared HTTP cache had nothing usable |
| `quota_consumed` | A request was charged against a provider's daily quota |
| `quota_exhausted` | A fetch was refused because the daily quota was spent |

`MetricEvent` carries `kind`, `provider`, `timestamp`, `attempt`,
`latency_ms`, `error_code`, `http_status`, `url`, and an `extra` mapping.
Cache events set `provider` to `None` and carry the request `url` instead —
the HTTP cache lives at the shared transport, below per-provider attribution.

For a per-call rollup without a hook, `response.summary.retries` reports how
many retries a single `forecast()` needed.

## OpenTelemetry

A prebuilt bridge ships as the `otel` extra:

```bash
pip install "omni-weather-forecast-apis[otel]"
```

```python
from omni_weather_forecast_apis.otel import create_otel_metrics_hook

client = await create_omni_weather(
    config,
    metrics_hooks=[create_otel_metrics_hook()],
)
```

The bridge records counters for requests, retries, cache outcomes, and quota
consumption, plus an `omni_weather.request.duration_ms` histogram. It uses the
globally configured OpenTelemetry meter provider, so configure your exporter
as usual before creating the client.

## Debug logging

The CLI's `--debug` flag turns on verbose logging to stderr and writes a `.log`
file next to the SQLite database (or `./omni-weather.log` when `--sqlite` is
omitted). See [CLI](cli.md#flags).

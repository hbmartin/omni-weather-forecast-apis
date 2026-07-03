# Extending

This library deliberately stops at *collecting and normalizing* forecasts.
Higher-level products — consensus/ensemble forecasts, forecast verification
and provider accuracy scoring — are meant to live in separate packages built
on three extension points.

## 1. Response hooks

Register callables that receive every completed `ForecastResponse`. Hooks
may be sync or async; failures are logged and never break the forecast.

```python
from omni_weather_forecast_apis.client import create_omni_weather
from omni_weather_forecast_apis.types import ForecastResponse


async def record_for_verification(response: ForecastResponse) -> None:
    """e.g. ship normalized forecasts to a verification store."""
    for result in response.results:
        ...


client = await create_omni_weather(
    config,
    response_hooks=[record_for_verification],
)
```

This is the natural seam for an **ensemble package** (compute a consensus
from `response.results` and publish it) or a **verification package**
(persist each forecast now, compare against observations later).

## 2. Custom provider plugins

Any object satisfying the `WeatherPlugin` protocol can be registered,
including from outside this package:

```python
from omni_weather_forecast_apis.plugins import register_plugin

register_plugin(my_plugin)
```

Subclass `BasePlugin`/`BasePluginInstance` from
`omni_weather_forecast_apis.plugins._base` to inherit config validation,
HTTP error mapping, and the normalized point builders.

## 3. The SQLite feature matrix

The CLI's SQLite output is a stable, documented schema (see
[CLI](cli.md#sqlite-output)). The `stacking_features` view exposes one row
per provider/model/hour with the forecast horizon and NWP run cycle —
exactly the shape an ensemble stacker or verification job needs:

```sql
SELECT valid_time, provider, model, horizon_hours, temperature
FROM stacking_features
WHERE valid_time_unix BETWEEN :start AND :end
ORDER BY valid_time, provider;
```

A verification project can join this view against observed weather by
`valid_time` and location to score each provider's historical accuracy; an
ensemble project can use it as a training feature matrix and weight
providers accordingly.

## Quota trackers

The daily-quota mechanism is also pluggable: implement the `QuotaTracker`
protocol (`get_usage` / `record_request`) to back quota accounting with your
own store (Redis, Postgres, ...) and pass it to the client:

```python
client = await create_omni_weather(config, quota_tracker=my_tracker)
```

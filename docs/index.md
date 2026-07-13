# omni-weather-forecast-apis

Async Python library that fans out forecast requests across multiple weather
providers and normalizes the results into one typed Pydantic schema. It
preserves provider-native cadence and time boundaries while converting units
and condition codes into a common representation.

## Features

- **Multi-provider fan-out** with async orchestration and partial-failure tolerance
- **Typed normalized schema** — common Pydantic models for minutely, hourly, daily, and alert data
- **Plugin architecture** — 13 providers with typed per-provider config validation
- **Resilient by default** — retries with exponential backoff (honoring `Retry-After`), conditional-request HTTP caching, connection pooling limits
- **Rate limiting and quotas** — global concurrency and RPS limits with per-provider overrides, plus per-provider daily quota caps
- **Secrets from the environment** — reference API keys as `${ENV_VAR}` placeholders instead of embedding them in config files
- **CLI** — loads a TOML config, queries providers, prints a table or JSON, and optionally persists normalized output to SQLite
- **Extensible** — response hooks and a documented SQLite schema for downstream ensemble and verification projects

## How it works

1. **Fan-out** — A `ForecastRequest` is dispatched concurrently to every
   enabled provider using async tasks, bounded by configurable concurrency
   and rate limits. Transient failures (network errors, timeouts, HTTP 429)
   are retried with exponential backoff.
2. **Normalize** — Each provider plugin converts its native response into the
   common `SourceForecast` schema, translating units (e.g. Fahrenheit to
   Celsius, mph to m/s) and mapping provider-specific condition codes to a
   shared `WeatherCondition` enum.
3. **Aggregate** — Results are collected into a single `ForecastResponse`.
   Providers that succeed return `ProviderSuccess` with their forecasts;
   providers that fail return `ProviderError` with a typed error code. The
   response always completes, even if some providers fail.

## Where to go next

- [Getting Started](getting-started.md) — install and run your first forecast
- [Configuration](configuration.md) — every knob in the TOML config
- [Providers](providers.md) — supported providers and their config keys
- [CLI](cli.md) — flags, output formats, and SQLite persistence
- [Scheduling](scheduling.md) — recurring collection with cron on Linux or launchd on macOS
- [Database Design](database.md) — relationships, table and column reference, indexes, migrations, and query patterns
- [Extending](extending.md) — plugins, response hooks, and building ensemble/verification tools on top
- [API Reference](api-reference.md) — generated from the source

# omni-weather-forecast-apis

[![PyPI](https://img.shields.io/pypi/v/omni-weather-forecast-apis.svg)](https://pypi.org/project/omni-weather-forecast-apis/)
[![CI](https://github.com/hbmartin/omni-weather-forecast-apis/actions/workflows/ci.yml/badge.svg)](https://github.com/hbmartin/omni-weather-forecast-apis/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with pyrefly](https://img.shields.io/badge/🪲-pyrefly-fe8801.svg)](https://pyrefly.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/hbmartin/omni-weather-forecast-apis)

Async Python library that fans out forecast requests across multiple weather providers and normalizes the results into one typed Pydantic schema. It preserves provider-native cadence and time boundaries while converting units and condition codes into a common representation.

Requires **Python 3.13 or newer**.

📖 **[Documentation site](https://hbmartin.github.io/omni-weather-forecast-apis/)**

## Contents

- [Features](#features)
- [Supported Providers](#supported-providers)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Library Usage](#library-usage)
- [CLI Usage](#cli-usage)
- [Observability](#observability)
- [Partial Failures](#partial-failures)
- [Normalized Schema](#normalized-schema)
- [Provider Configuration Reference](#provider-configuration-reference)
- [SQLite Output](#sqlite-output)
- [Extending](#extending)
- [Documentation](#documentation)
- [Development](#development)

## Features

- **Multi-provider fan-out** with async orchestration and partial-failure tolerance
- **Typed normalized schema** — common Pydantic models for minutely, hourly, daily, and alert data
- **Plugin architecture** — 13 providers with typed per-provider config validation
- **Resilient by default** — retries with exponential backoff (honoring `Retry-After`), conditional-request HTTP caching (`ETag`/`Last-Modified`/`Expires`), and explicit connection pool limits
- **Rate limiting and quotas** — global concurrency and RPS limits with per-provider overrides, plus per-provider daily quota caps
- **Secrets from the environment** — reference API keys as `${ENV_VAR}` placeholders instead of embedding them in config files
- **CLI** — loads a TOML config, queries providers, prints a table or JSON, and optionally persists normalized output to SQLite
- **Extensible** — response hooks and a documented SQLite feature view for downstream ensemble/verification projects

## Supported Providers

Three of the thirteen providers need no API key at all, so you can try the
library without signing up for anything.

| Provider | Plugin ID | API key | Minutely | Hourly | Daily | Alerts | Multi-model | Coverage |
|----------|-----------|---------|---------:|-------:|------:|:------:|:-----------:|----------|
| [Open-Meteo](https://open-meteo.com/) | `open_meteo` | Optional | 1 h | 16 d | 16 d | — | ✅ | Global |
| [MET Norway](https://api.met.no/) | `met_norway` | None | — | 9 d | — | — | — | Nordics |
| [NWS / NOAA](https://www.weather.gov/documentation/services-web-api) | `nws` | None | — | ✅ | ✅ | ✅ | — | US only |
| [OpenWeather](https://openweathermap.org/api) | `openweather` | Required | 1 h | 48 h | 8 d | ✅ | — | Global |
| [WeatherAPI](https://www.weatherapi.com/) | `weatherapi` | Required | — | 14 d | 14 d | ✅ | — | Global |
| [Tomorrow.io](https://www.tomorrow.io/) | `tomorrow_io` | Required | 1 h | 5 d | 6 d | — | — | Global |
| [Visual Crossing](https://www.visualcrossing.com/) | `visual_crossing` | Required | — | 15 d | 15 d | ✅ | — | Global |
| [Weatherbit](https://www.weatherbit.io/) | `weatherbit` | Required | — | 10 d | 16 d | — | — | Global |
| [Meteosource](https://www.meteosource.com/) | `meteosource` | Required | 1 h | 7 d | 30 d | ✅ | — | Global |
| [Pirate Weather](https://pirateweather.net/) | `pirate_weather` | Required | 1 h | 48 h | 8 d | ✅ | — | Global |
| [Stormglass](https://stormglass.io/) | `stormglass` | Required | — | ✅ | — | — | ✅ | Global |
| [Weather Unlocked](https://developer.weatherunlocked.com/) | `weather_unlocked` | Required | — | ✅ | ✅ | — | — | Global |
| [Google Weather](https://developers.google.com/maps/documentation/weather) | `google_weather` | Required | — | 10 d | 10 d | — | — | Global |

The minutely, hourly, and daily columns give each provider's **maximum forecast
horizon**. `✅` means the granularity is supported but the plugin declares no
horizon bound, and `—` means it is not supported at all. **Multi-model**
providers return several independent forecasts per request — Open-Meteo exposes
named numerical weather models (`best_match`, `ecmwf_ifs025`, …) and Stormglass
returns multiple upstream sources — which is what makes them useful for
ensembles.

MET Norway and NWS additionally require a `user_agent` identifying your
application; Weather Unlocked uses an `app_id` + `app_key` pair rather than a
single key. Pirate Weather's hourly horizon extends to 168 h when
`extend_hourly = true`. See the [provider configuration
reference](#provider-configuration-reference) for every key each plugin accepts.

## Quick Start

Open-Meteo, MET Norway, and NWS need no API keys, so this runs end to end
without any signup. No install step — [uv](https://docs.astral.sh/uv/) fetches
the package into a throwaway environment:

```bash
cat > config.toml << 'EOF'
[[providers]]
plugin_id = "open_meteo"
config = { models = ["best_match", "ecmwf_ifs025"] }

[[providers]]
plugin_id = "met_norway"
config = { user_agent = "MyApp/1.0 you@yourdomain.com" }

[[providers]]
plugin_id = "nws"
config = { user_agent = "MyApp/1.0 you@yourdomain.com" }
EOF

uvx --from "omni-weather-forecast-apis[cli]" omni-weather \
  --config ./config.toml \
  --lat 40.7128 \
  --lon -74.0060 \
  --sqlite ./forecasts.sqlite
```

Put a real contact address in `user_agent` before running this. MET Norway's
terms require one to identify the caller, and their API rejects placeholder
domains such as `example.com` with a `403 Forbidden`.

Which prints:

```
                              Run 1 — 3/3 succeeded
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Provider   ┃ Status ┃ Latency ┃ Hourly ┃ Daily ┃ Minutely ┃ Alerts ┃ Detail      ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━┩
│ open_meteo │   OK   │   924ms │    336 │    14 │        0 │      - │ 2 source(s) │
│ met_norway │   OK   │   705ms │     90 │     0 │        0 │      - │ 1 source(s) │
│ nws        │   OK   │   283ms │    156 │     8 │        0 │      - │ 1 source(s) │
└────────────┴────────┴─────────┴────────┴───────┴──────────┴────────┴─────────────┘
                       Saved to forecasts.sqlite in 924ms
```

Open-Meteo contributes two sources because two models were requested. Every
forecast is now in `forecasts.sqlite`, normalized and ready to
[query](#sqlite-output).

## Installation

```bash
# As a library dependency
pip install omni-weather-forecast-apis

# With the interactive CLI, discovery, diagnostics, and rich output
pip install "omni-weather-forecast-apis[cli]"

# Run the CLI without installing anything
uvx --from "omni-weather-forecast-apis[cli]" omni-weather --help
```

Requires Python 3.13 or newer. The console-script wrapper is installed with the
base package, but CLI commands require the `cli` extra. Without it the wrapper
exits with the exact installation command instead of failing with an import
traceback.

Contributing to this repository instead? See [Development](#development) for the
`uv sync` workflow.

## How It Works

1. **Fan-out** — A `ForecastRequest` is dispatched concurrently to every enabled provider using async tasks, bounded by configurable concurrency and rate limits.
2. **Normalize** — Each provider plugin converts its native response into the common `SourceForecast` schema, translating units (e.g. Fahrenheit to Celsius, mph to m/s) and mapping provider-specific condition codes to a shared `WeatherCondition` enum.
3. **Aggregate** — Results are collected into a single `ForecastResponse`. Providers that succeed return `ProviderSuccess` with their forecasts; providers that fail return `ProviderError` with a typed error code. The response always completes, even if some providers fail.

## Configuration

The client and CLI both use a TOML configuration file that matches `OmniWeatherConfig`.

```toml
latitude = 40.7128
longitude = -74.0060
sqlite = "forecasts.sqlite"
granularity = ["hourly", "daily"]
language = "en"
include_raw = false
debug = false
default_timeout_ms = 10000

[rate_limiting]
max_in_flight = 10
max_requests_per_second = 20

[retry]
max_attempts = 3          # total attempts per provider fetch; 1 disables retries
initial_backoff_ms = 500
max_backoff_ms = 8000
backoff_multiplier = 2.0
jitter = true

[http]
max_connections = 20
max_keepalive_connections = 10
connect_timeout_ms = 5000
cache_enabled = true      # conditional-request HTTP cache (ETag/Last-Modified/Expires)
cache_max_entries = 256
raw_archive_enabled = true  # archive raw HTTP payloads next to the SQLite database

[[providers]]
plugin_id = "open_meteo"
enabled = true
config = { models = ["best_match", "ecmwf_ifs025"] }

[[providers]]
plugin_id = "met_norway"
enabled = true
config = { user_agent = "MyApp/1.0 you@yourdomain.com", variant = "complete" }

[[providers]]
plugin_id = "openweather"
enabled = true
config = { api_key = "${OPENWEATHER_API_KEY}", units = "metric" }
rate_limit_rps = 5
timeout_ms = 8000
max_requests_per_day = 900
```

### Retries

Transient failures — network errors, timeouts, and HTTP 429 rate limits — are retried with exponential backoff and jitter. A server-provided `Retry-After` header is honored; retries are abandoned when it exceeds 60 seconds. Non-transient failures such as auth errors are never retried. Set a per-provider `retry` table on a registration to override the global policy.

### HTTP caching and connection limits

The shared HTTP client is powered by [HTTPX2](https://httpx2.pydantic.dev/), uses explicit connection pool limits and a connect timeout, and caches GET responses in memory. Fresh responses (`Cache-Control: max-age` / `Expires`) are served without a network round-trip; stale responses carrying `ETag`/`Last-Modified` validators are revalidated with conditional requests and reused on `304 Not Modified`. Responses that declare `Vary` are only reused for requests sending the same values for the named headers (`Vary: *` is never cached). Requests carrying `Authorization` or `Cookie` headers bypass the shared cache. MET Norway's terms of service require conditional requests and the NWS strongly encourages caching. Disable with `cache_enabled = false` under `[http]`.

When persisting to SQLite, every network response is additionally archived as gzipped JSONL (one line per response: timestamp, method, URL, status, body) into a `raw/` directory next to the database — one file per invocation, linked from `forecast_runs.raw_archive_path`. The archive makes historical runs reparseable if a parser bug is ever found. URLs are stored verbatim, including API keys in query strings, so keep archives out of version control (the repo ignores `raw/`). Disable with `--no-raw-archive` or `raw_archive_enabled = false` under `[http]`. Files accumulate until deleted manually.

### Daily quotas

Most free tiers are capped per day, not per second. Set `max_requests_per_day` on a provider registration and the client returns a `quota_exceeded` error once the day's budget (UTC) is spent instead of burning through it. Each fetch attempt counts one request — retries are real HTTP calls against the provider's cap, so a single `forecast()` call may consume up to `retry.max_attempts` units when transient failures trigger retries. This deliberately mirrors provider-side accounting; lower `max_attempts` if you need a tighter bound per call. The CLI persists counts in the SQLite database (`provider_quota_usage` table) so limits survive across runs; library users can pass any `QuotaTracker` implementation with atomic `try_consume` support (`InMemoryQuotaTracker` is the default, `SqliteQuotaTracker` is bundled in `omni_weather_forecast_apis.quota`).

### API keys from environment variables

Any string value inside a provider `config` block can reference an environment variable instead of embedding a secret:

```toml
# whole-string reference
config = { api_key = "${OPENWEATHER_API_KEY}" }

# explicit marker table (equivalent)
config = { api_key = { env = "OPENWEATHER_API_KEY" } }
```

Resolution happens at client initialization and recurses through nested tables and arrays. A placeholder naming an unset variable becomes a per-provider initialization error; other providers are unaffected. Partial interpolation (`"prefix-${VAR}"`) is not supported — only whole-string placeholders are resolved.

## Library Usage

```python
import asyncio

from omni_weather_forecast_apis import (
    ForecastRequest,
    Granularity,
    OmniWeatherConfig,
    ProviderError,
    ProviderRegistration,
    ProviderId,
    ProviderSuccess,
    create_omni_weather,
)


async def main() -> None:
    config = OmniWeatherConfig(
        providers=[
            ProviderRegistration(
                plugin_id=ProviderId.OPEN_METEO,
                config={"models": ["best_match"]},
            ),
            ProviderRegistration(
                plugin_id=ProviderId.MET_NORWAY,
                config={"user_agent": "MyApp/1.0 you@yourdomain.com"},
            ),
        ],
    )

    async with await create_omni_weather(config) as client:
        response = await client.forecast(
            ForecastRequest(
                latitude=34.2484,
                longitude=-117.1931,
                granularity=[Granularity.HOURLY, Granularity.DAILY],
            ),
        )
        print(response.summary)
        # ForecastResponseSummary(total=2, succeeded=2, failed=0)

        for result in response.results:
            match result:
                case ProviderSuccess(provider=pid, forecasts=forecasts):
                    for fc in forecasts:
                        for pt in fc.hourly:
                            print(f"{pid} {pt.timestamp}: {pt.temperature}°C, {pt.condition}")
                case ProviderError(provider=pid, error=err):
                    print(f"{pid} failed: {err.code} — {err.message}")


asyncio.run(main())
```

Example output:

```
ProviderId.OPEN_METEO 2026-03-13 18:00:00+00:00: 12.3°C, WeatherCondition.PARTLY_CLOUDY
ProviderId.OPEN_METEO 2026-03-13 19:00:00+00:00: 11.8°C, WeatherCondition.OVERCAST
ProviderId.MET_NORWAY 2026-03-13 18:00:00+00:00: 12.1°C, WeatherCondition.RAIN
...
```

## CLI Usage

The easiest first run is the interactive setup wizard:

```bash
omni-weather init
```

It requires default coordinates, recommends keyless Open-Meteo, groups the
remaining providers by authentication needs, chooses a platform-native SQLite
path, and lets you select one or more granularities. The generated TOML is
parsed and fully validated before an exact preview is shown. Credential prompts
are masked, but the selected values are intentionally stored in the TOML and
shown in that preview; protect the terminal session as well as the resulting
owner-only (`0600` on POSIX) file. After saving, the wizard optionally installs
a daily forecast job at a chosen local time using cron on Linux, launchd on
macOS, or Windows Task Scheduler. Scheduling defaults to off; the final test
forecast defaults to yes.

If a forecast command omits `--config`, configuration is resolved in this
order:

1. The platform-native `omni-weather/config.toml` path.
2. The legacy `~/.config/omni_weather_forecast_apis.toml` path.
3. Interactive setup when neither file exists.

Automatic setup requires interactive stdin and stderr. In a pipe, cron job, or
other non-interactive process, the CLI exits `2` and prints the expected path
and `init` command. An explicit missing `--config` is always an error. When
automatic setup succeeds, the original forecast request runs immediately with
all its CLI overrides. Wizard messages go to stderr, so JSON, CSV, and NDJSON
stdout remains machine-readable.

Default platform paths (with platform conventions such as XDG overrides still
honored) are:

| Platform | Configuration | SQLite data |
|----------|---------------|-------------|
| Linux | `~/.config/omni-weather/config.toml` | `~/.local/share/omni-weather/forecasts.sqlite` |
| macOS | `~/Library/Application Support/omni-weather/config.toml` | `~/Library/Application Support/omni-weather/forecasts.sqlite` |
| Windows | `%LOCALAPPDATA%\omni-weather\config.toml` | `%LOCALAPPDATA%\omni-weather\forecasts.sqlite` |

```bash
omni-weather \
  --config ./config.toml \
  --lat 34.2484 \
  --lon -117.1931 \
  --sqlite ./forecasts.sqlite

# Query only specific providers
omni-weather \
  --config ./config.toml \
  --lat 34.2484 \
  --lon -117.1931 \
  --sqlite ./forecasts.sqlite \
  --provider open_meteo \
  --provider nws \
  --granularity hourly

# Emit the full normalized response as JSON (no SQLite required)
omni-weather \
  --config ./config.toml \
  --lat 34.2484 \
  --lon -117.1931 \
  --format json | jq '.results[] | {provider, status}'

# Pipe flattened per-point rows into data tools
omni-weather --config ./config.toml --lat 34.2 --lon -117.2 \
  --format csv > forecast.csv
omni-weather --config ./config.toml --lat 34.2 --lon -117.2 \
  --format ndjson | jq 'select(.type == "forecast_point") | .temperature'

# Browse setup requirements and signup links
omni-weather providers

# Aggregate local configuration diagnostics (no network requests)
omni-weather doctor

# Opt in to live checks, optionally for selected providers
omni-weather doctor --live --provider open_meteo
```

The CLI performs one forecast collection per invocation. `omni-weather init`
can install a daily platform-native job. For custom cadences and manual setup,
see the [Scheduling guide](https://hbmartin.github.io/omni-weather-forecast-apis/scheduling/).

`csv` and `ndjson` emit one row/line per forecast data point, flattened with
`provider`, `model`, and `granularity` (`minutely` / `hourly` / `daily`)
columns followed by the normalized point fields. `ndjson` lines carry a
`type` field (`forecast_point`, `alert`, or `provider_error`); CSV omits
alerts (noted on stderr) and reports provider errors on stderr only.

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--config PATH` | No | platform path, then legacy path | Path to TOML configuration file |
| `--lat FLOAT` | No | config value | Latitude (-90 to 90); overrides config |
| `--lon FLOAT` | No | config value | Longitude (-180 to 180); overrides config |
| `--sqlite PATH` | No | config value | SQLite database output path; overrides config. Persistence is skipped when neither is set |
| `--format FMT` | No | `table` | Output format: `table` (human-readable summary), `json` (full normalized response), `csv` (one flattened row per data point), or `ndjson` (one JSON object per line, typed `forecast_point` / `alert` / `provider_error`) |
| `--provider ID` | No | all enabled | Restrict to specific provider(s); repeatable |
| `--granularity GRAN` | No | config value | `minutely`, `hourly`, or `daily`; repeatable |
| `--language LANG` | No | config value | Provider language preference |
| `--include-raw` | No | config value | Persist raw provider payloads |
| `--no-raw-archive` | No | archiving on | Skip writing the raw HTTP payload archive (`raw/<UTC timestamp>.jsonl.gz` next to the SQLite database) |
| `--timeout-ms MS` | No | config value | Override the default timeout; provider-specific timeouts still take precedence |
| `--debug` | No | config value | Enable verbose debug output to stderr and write a `.log` file next to the SQLite database, or `./omni-weather.log` when SQLite is omitted |

`omni-weather providers` shows every provider's coverage, supported
granularities, authentication shape, and official setup link. `omni-weather
doctor` aggregates TOML, coordinates, environment references, provider
settings, granularity compatibility, output paths, duplicates, and POSIX
permission checks. It also reports whether the platform-native daily schedule
for the selected config is installed; a missing schedule is highlighted as a
warning and does not make `doctor` fail. It never prints resolved environment
values. `--provider` narrows provider-specific checks while retaining top-level
checks. Only `--live` contacts providers; live checks do not persist results,
but they can consume API quota and be subject to rate limits.

**Exit codes:** forecast and doctor return `0` when required checks or providers
succeed and `1` for provider/diagnostic failures. Warnings alone return `0`.
Invalid invocation, load failures outside doctor, and unexpected operational
errors return `2`. Cancelling explicit `init` returns `0`; cancelling automatic
first-run setup returns `2`. Pressing Ctrl+C while a command is running prints
`Aborted.` without a traceback and returns `130`.

## Observability

Beyond the structured per-provider log events (`log_hooks`), the client
emits typed **metric events** for every request attempt, retry, HTTP cache
lookup, and quota consumption. Register any callable as a `MetricsHook` —
no extra dependencies required:

```python
from omni_weather_forecast_apis import MetricEvent, MetricKind, create_omni_weather

def record(event: MetricEvent) -> None:
    if event.kind is MetricKind.REQUEST_END:
        print(event.provider, event.latency_ms, event.error_code)

client = await create_omni_weather(config, metrics_hooks=[record])
```

`MetricKind` covers `request_start`, `request_end`, `retry_scheduled`,
`cache_hit`, `cache_miss`, `quota_consumed`, and `quota_exhausted`. Cache
events carry the request `url` instead of a provider (the HTTP cache is
shared across providers). `response.summary.retries` reports how many
retries a `forecast()` call needed.

For OpenTelemetry, install the `otel` extra and use the prebuilt bridge:

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

The bridge records counters for requests, retries, cache outcomes, and
quota, plus a `omni_weather.request.duration_ms` histogram.

## Partial Failures

The library is designed for partial-failure tolerance. When some providers fail (network errors, rate limits, auth issues), the response still completes with results from the providers that succeeded.

Each entry in `response.results` is either a `ProviderSuccess` or `ProviderError`, distinguished by the `status` field. The `response.summary` provides counts at a glance:

```python
response.summary
# ForecastResponseSummary(total=3, succeeded=2, failed=1)
```

`ProviderError` includes a typed `error.code` (`AUTH_FAILED`, `RATE_LIMITED`, `QUOTA_EXCEEDED`, `TIMEOUT`, `NETWORK`, `PARSE`, `NOT_AVAILABLE`, `UNKNOWN`), a human-readable `error.message`, the `error.http_status` when available, and `error.latency_ms` for how long the request ran before failing.

The CLI reflects this in exit codes: `0` means all providers succeeded, `1` means at least one failed (but partial results are still written to SQLite), and `2` means invalid arguments or a configuration/load error.

## Normalized Schema

All provider responses are normalized into a common set of Pydantic models. Units are standardized: temperatures in °C, wind speeds in m/s, pressure in hPa, precipitation in mm, visibility in km.

> **A note on pressure data.** Pressure is the least reliable field providers report — implausible sea-level values have been observed in the wild (Stormglass emitting 885 hPa, Weatherbit 1074 hPa). And if you compare `pressure_sea` against a personal weather station, calibrate the station first: consumer stations report an *absolute* (station-level) pressure and a *relative* (sea-level) pressure, and the relative reading requires an elevation offset to be configured — an uncalibrated station at altitude can read more than 150 hPa below the true sea-level value while its absolute sensor is perfectly healthy. Pressure plausibility checks are planned; the author will be working on this soon.

### `WeatherDataPoint` (hourly)

| Field | Type | Unit |
|-------|------|------|
| `temperature`, `apparent_temperature`, `dew_point` | float \| None | °C |
| `humidity` | float \| None | % (0-100) |
| `wind_speed`, `wind_gust` | float \| None | m/s |
| `wind_direction` | float \| None | degrees |
| `pressure_sea`, `pressure_surface` | float \| None | hPa |
| `precipitation`, `rain`, `snow` (liquid equivalent), `snow_depth` | float \| None | mm |
| `snowfall_depth` (new snow depth; providers report either this or `snow`, not both) | float \| None | mm |
| `precipitation_probability` | float \| None | 0-1 |
| `cloud_cover`, `cloud_cover_low`, `cloud_cover_mid`, `cloud_cover_high` | float \| None | % |
| `visibility` | float \| None | km |
| `uv_index` | float \| None | 0-11+ |
| `solar_radiation_ghi`, `solar_radiation_dni`, `solar_radiation_dhi` | float \| None | W/m² |
| `condition` | WeatherCondition \| None | enum |
| `is_day` | bool \| None | |

### `DailyDataPoint`

| Field | Type | Unit |
|-------|------|------|
| `date` | date | |
| `temperature_max`, `temperature_min` | float \| None | °C |
| `apparent_temperature_max`, `apparent_temperature_min` | float \| None | °C |
| `wind_speed_max`, `wind_gust_max` | float \| None | m/s |
| `precipitation_sum`, `rain_sum`, `snowfall_sum` (liquid equivalent), `snowfall_depth_sum` (depth) | float \| None | mm |
| `precipitation_probability_max` | float \| None | 0-1 |
| `cloud_cover_mean` | float \| None | % |
| `humidity_mean` | float \| None | % |
| `uv_index_max` | float \| None | 0-11+ |
| `sunrise`, `sunset`, `moonrise`, `moonset` | datetime \| None | UTC |
| `moon_phase` | float \| None | 0-1 |
| `daylight_duration` | float \| None | seconds |
| `condition` | WeatherCondition \| None | enum |
| `summary` | str \| None | |

### `MinutelyDataPoint`

| Field | Type | Unit |
|-------|------|------|
| `precipitation_intensity` | float \| None | mm/h |
| `precipitation_probability` | float \| None | 0-1 |

### `WeatherAlert`

| Field | Type |
|-------|------|
| `sender_name` | str |
| `event` | str |
| `start`, `end` | datetime (UTC) |
| `description` | str |
| `severity` | `EXTREME` \| `SEVERE` \| `MODERATE` \| `MINOR` \| `UNKNOWN` |
| `url` | str \| None |

### `WeatherCondition` enum

`CLEAR`, `MOSTLY_CLEAR`, `PARTLY_CLOUDY`, `MOSTLY_CLOUDY`, `OVERCAST`, `FOG`, `DRIZZLE`, `LIGHT_RAIN`, `RAIN`, `HEAVY_RAIN`, `FREEZING_RAIN`, `LIGHT_SNOW`, `SNOW`, `HEAVY_SNOW`, `SLEET`, `HAIL`, `THUNDERSTORM`, `THUNDERSTORM_RAIN`, `THUNDERSTORM_HEAVY`, `DUST`, `SAND`, `SMOKE`, `HAZE`, `TORNADO`, `HURRICANE`, `UNKNOWN`

## Provider Configuration Reference

Each provider accepts a typed config dict. Required fields are marked with **bold**.

| Provider | Config Keys |
|----------|-------------|
| `open_meteo` | `api_key`?, `models` (default: `["best_match"]`), `extra_hourly_vars`?, `extra_daily_vars`? |
| `met_norway` | **`user_agent`**, `altitude`?, `variant` (`"compact"` \| `"complete"`, default: `"complete"`) |
| `nws` | **`user_agent`**, `grid_override`? (`{office, grid_x, grid_y}`) |
| `openweather` | **`api_key`**, `exclude`?, `units` (`"standard"` \| `"metric"` \| `"imperial"`, default: `"metric"`) |
| `weatherapi` | **`api_key`**, `days` (1-14, default: 7), `aqi` (default: false), `alerts` (default: true) |
| `tomorrow_io` | **`api_key`**, `fields`? |
| `visual_crossing` | **`api_key`**, `include` (default: `"hours,days,alerts"`) |
| `weatherbit` | **`api_key`**, `hours` (1-240, default: 48), `units` (`"M"` \| `"S"` \| `"I"`, default: `"M"`) |
| `meteosource` | **`api_key`**, `sections` (default: `["current", "hourly", "daily"]`) |
| `pirate_weather` | **`api_key`**, `extend_hourly` (default: false), `version` (`"1"` \| `"2"`, default: `"2"`) |
| `stormglass` | **`api_key`**, `sources` (default: `["sg"]`), `params` (list of weather variables) |
| `weather_unlocked` | **`app_id`**, **`app_key`**, `lang`? |
| `google_weather` | **`api_key`**, `hours` (1-240, default: 48), `days` (1-10, default: 10) |

## SQLite Output

The CLI creates a normalized database with these tables:

| Table | Contents |
|-------|----------|
| `forecast_runs` | Request metadata per invocation |
| `provider_results` | One row per provider outcome (success or error) |
| `source_forecasts` | One row per model/source forecast within a provider |
| `minutely_points` | Precipitation intensity at minute intervals |
| `hourly_points` | Normalized hourly forecast rows |
| `daily_points` | Normalized daily summary rows |
| `alerts` | Weather alerts and warnings |
| `provider_logs` | Per-provider lifecycle log entries (`start`, `retry`, `success`, `error`) per run |
| `provider_quota_usage` | Requests per provider per UTC day, used for daily quota enforcement |

See the [database design and structure guide](docs/database.md) for the full
relationship model, column and unit reference, indexes, deletion semantics,
schema evolution, and query examples.

The `stacking_features` SQL view joins hourly points with their run, provider,
model, run cycle, and forecast horizon — a ready-made feature matrix for
downstream ensemble/verification work. Select one run and one exact valid time
to keep successive runs and neighboring forecast hours separate:

```sql
WITH latest_run AS (
    SELECT MAX(id) AS run_id FROM forecast_runs
), target_time AS (
    SELECT MIN(valid_time_unix) AS valid_time_unix
    FROM stacking_features
    WHERE run_id = (SELECT run_id FROM latest_run)
      AND horizon_hours >= 24
)
SELECT valid_time, provider, model,
       ROUND(temperature, 1) AS temp_c,
       ROUND(wind_speed, 1) AS wind_ms
FROM stacking_features
WHERE run_id = (SELECT run_id FROM latest_run)
  AND valid_time_unix = (SELECT valid_time_unix FROM target_time)
ORDER BY provider, model;
```

```
valid_time                 provider    model         temp_c  wind_ms
-------------------------  ----------  ------------  ------  -------
2026-03-14T05:00:00+00:00  met_norway  met_norway    23.2    4.5
2026-03-14T05:00:00+00:00  nws         nws           25.0    4.5
2026-03-14T05:00:00+00:00  open_meteo  best_match    22.0    5.1
2026-03-14T05:00:00+00:00  open_meteo  ecmwf_ifs025  23.2    3.3
```

Four independent 24-hour-ahead forecasts for the same point and time, already
unit-normalized — the input a blending or verification model wants. `run_id`
separates successive requests, while `run_cycle`, `horizon_hours`, and
`fetched_at_unix` describe forecast age and provider fetch timing.

## Extending

Consensus/ensemble forecasting and forecast verification are intended to live in separate packages built on three extension points — see the [Extending guide](https://hbmartin.github.io/omni-weather-forecast-apis/extending/) for details:

- **Response hooks** — sync or async callables that receive every completed `ForecastResponse`:

  ```python
  async def record_for_verification(response: ForecastResponse) -> None:
      ...

  client = await create_omni_weather(config, response_hooks=[record_for_verification])
  ```

- **Custom provider plugins** — pass any `WeatherPlugin` implementations to `create_omni_weather(config, plugins=[...])` for a per-client plugin set, or register globally with `omni_weather_forecast_apis.plugins.register_plugin` (the global registry backs the CLI and is the fallback when `plugins` is omitted).
- **The SQLite feature matrix** — query the `stacking_features` view for aligned per-provider hourly forecasts with horizons and run cycles.

## Documentation

The documentation site is built with [Zensical](https://zensical.org/)
(configured in `zensical.toml`) from the `docs/` directory:

```bash
uv sync --group docs
uv run zensical serve
```

## Development

```bash
# Set up the repository (Python 3.13+)
uv sync --extra cli

# Lint, format, and type-check
uv run ruff check src --fix
uv run ruff format src tests
uv run pyrefly check src
uv run ty check src

# Dependency, package, and complexity checks
uv run deptry src
uv run pyroma --min 8 .
uv run lizard -Eduplicate -C 27 src

# Tests and the 88% coverage floor
uv run pytest tests/ --cov=src --cov-report=term-missing
```

## License

[Apache 2.0](LICENSE)

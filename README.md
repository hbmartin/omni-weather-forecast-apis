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

## Features

- **Multi-provider fan-out** with async orchestration and partial-failure tolerance
- **Typed normalized schema** — common Pydantic models for minutely, hourly, daily, and alert data
- **Plugin architecture** — 16 providers with typed per-provider config validation
- **Resilient by default** — retries with exponential backoff (honoring `Retry-After`), conditional-request HTTP caching (`ETag`/`Last-Modified`/`Expires`), and explicit connection pool limits
- **Rate limiting and quotas** — global concurrency and RPS limits with per-provider overrides, plus per-provider daily quota caps
- **Secrets from the environment** — reference API keys as `${ENV_VAR}` placeholders instead of embedding them in config files
- **CLI** — loads a TOML config, queries providers, prints a table or JSON, and optionally persists normalized output to SQLite
- **Replayable raw archives** — SQLite runs store network responses in a unique gzipped JSONL file per invocation
- **Extensible** — response hooks and a documented SQLite feature view for downstream ensemble/verification projects

## Supported Providers

Four of the sixteen providers need no API key at all, so you can try the
library without signing up for anything.

| Provider | Plugin ID | API key | Minutely | Hourly | Daily | Alerts | Multi-model | Coverage |
|----------|-----------|---------|---------:|-------:|------:|:------:|:-----------:|----------|
| [Open-Meteo](https://open-meteo.com/) | `open_meteo` | Optional | 1 h | 16 d | 16 d | — | ✅ | Global |
| [MET Norway](https://api.met.no/) | `met_norway` | None | — | 9 d | — | — | — | Nordics |
| [NWS / NOAA](https://www.weather.gov/documentation/services-web-api) | `nws` | None | — | ✅ | ✅ | ✅ | — | US only |
| [NOAA NBM](https://vlab.noaa.gov/web/mdl/nbm) (via [IEM](https://mesonet.agron.iastate.edu/mos/)) | `nbm` | None | — | 72 h (3-hourly) | — | — | — | US only |
| [OpenWeather](https://openweathermap.org/api) | `openweather` | Required | 1 h | 48 h | 8 d | ✅ | — | Global |
| [WeatherAPI](https://www.weatherapi.com/) | `weatherapi` | Required | — | 14 d | 14 d | ✅ | — | Global |
| [Tomorrow.io](https://www.tomorrow.io/) | `tomorrow_io` | Required | 1 h | 5 d | 6 d | — | — | Global |
| [Visual Crossing](https://www.visualcrossing.com/) | `visual_crossing` | Required | — | 15 d | 15 d | ✅ | — | Global |
| [Weatherbit](https://www.weatherbit.io/) | `weatherbit` | Required | — | 10 d | 16 d | — | — | Global |
| [Meteosource](https://www.meteosource.com/) | `meteosource` | Required | 1 h | 7 d | 30 d | ✅ | — | Global |
| [Pirate Weather](https://pirateweather.net/) | `pirate_weather` | Required | 1 h | 48 h | 8 d | ✅ | — | Global |
| [Stormglass](https://stormglass.io/) | `stormglass` | Required | — | ✅ | — | — | ✅ | Global |
| [Google Weather](https://developers.google.com/maps/documentation/weather) | `google_weather` | Required | — | 10 d | 10 d | — | — | Global |
| [Met Office](https://datahub.metoffice.gov.uk/) | `met_office` | Required | — | 48 h | 6 d | — | — | Global |
| [Xweather](https://www.xweather.com/) | `xweather` | Required | — | 10 d | 15 d | — | — | Global |
| [Apple WeatherKit](https://developer.apple.com/weatherkit/) | `weatherkit` | Required | 1 h | 10 d | 10 d | ✅ | — | Global |

The minutely, hourly, and daily columns give each provider's **maximum forecast
horizon**. `✅` means the granularity is supported but the plugin declares no
horizon bound, and `—` means it is not supported at all. **Multi-model**
providers return several independent forecasts per request — Open-Meteo exposes
named numerical weather models (`best_match`, `ecmwf_ifs025`, …) and Stormglass
returns multiple upstream sources — which is what makes them useful for
ensembles.

Every key each plugin accepts, along with per-provider unit and semantics
caveats, is in the [Providers
reference](https://hbmartin.github.io/omni-weather-forecast-apis/providers/).

### Upgrade note: Weather Unlocked removed

The `weather_unlocked` provider has been removed. Existing configurations that
refer to that plugin ID no longer validate and must remove the registration or
replace it with another supported provider. There is no automatic provider
substitution because credentials and forecast semantics differ by service.

## Quick Start

Open-Meteo, MET Norway, NWS, and NBM need no API keys, so this runs end to end
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

[[providers]]
plugin_id = "nbm"
config = { station_id = "KNYC" }  # nearest NBM/METAR station to your coordinates
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

`--config` is optional — it defaults to a TOML file in your platform's config
directory, which `omni-weather init` creates for you. It is passed explicitly
above only so the example is self-contained. `--lat`, `--lon`, and `--sqlite`
likewise fall back to the config file when omitted.

Which prints:

```
                              Run 1 — 4/4 succeeded
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Provider   ┃ Status ┃ Latency ┃ Hourly ┃ Daily ┃ Minutely ┃ Alerts ┃ Detail      ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━┩
│ open_meteo │   OK   │   924ms │    336 │    14 │        0 │      - │ 2 source(s) │
│ met_norway │   OK   │   705ms │     90 │     0 │        0 │      - │ 1 source(s) │
│ nws        │   OK   │   283ms │    156 │     8 │        0 │      - │ 1 source(s) │
│ nbm        │   OK   │   410ms │     25 │     0 │        0 │      - │ 1 source(s) │
└────────────┴────────┴─────────┴────────┴───────┴──────────┴────────┴─────────────┘
                       Saved to forecasts.sqlite in 924ms
```

Open-Meteo contributes two sources because two models were requested. Every
forecast is now in `forecasts.sqlite`, normalized and ready to query.

Prefer to be walked through it? `omni-weather init` runs an interactive setup
wizard that collects coordinates, providers, and credentials, and can install a
daily collection job.

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

## Library Usage

```python
import asyncio

from omni_weather_forecast_apis import (
    ForecastRequest,
    Granularity,
    OmniWeatherConfig,
    ProviderRegistration,
    ProviderId,
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
                timezone="America/Los_Angeles",
            ),
        )
        print(response.summary)
        # ForecastResponseSummary(total=2, succeeded=2, failed=0)


asyncio.run(main())
```

Each entry in `response.results` is a `ProviderSuccess` or a `ProviderError`,
discriminated by `status` — pattern-match on them to read forecasts and typed
error codes. Pass the location's IANA `timezone` when requesting daily data or
provider-local wall times. If it is omitted, plugins that need it perform an
uncached Open-Meteo lookup; the CLI supplies and persistently caches this value
automatically when SQLite output is enabled. CLI cache entries retain six
coordinate decimals and are refreshed after 30 days. See [Getting
Started](https://hbmartin.github.io/omni-weather-forecast-apis/getting-started/)
and the [Normalized
Schema](https://hbmartin.github.io/omni-weather-forecast-apis/schema/).

## Documentation

Full documentation lives at
**[hbmartin.github.io/omni-weather-forecast-apis](https://hbmartin.github.io/omni-weather-forecast-apis/)**.

| Guide | Contents |
|-------|----------|
| [Getting Started](https://hbmartin.github.io/omni-weather-forecast-apis/getting-started/) | Install, interactive setup, first forecast, library usage |
| [Configuration](https://hbmartin.github.io/omni-weather-forecast-apis/configuration/) | Every TOML option — retries, HTTP cache, raw payload archive, daily quotas, `${ENV_VAR}` placeholders |
| [Providers](https://hbmartin.github.io/omni-weather-forecast-apis/providers/) | Per-provider config keys, and the unit/semantics caveats worth knowing before comparing values |
| [CLI](https://hbmartin.github.io/omni-weather-forecast-apis/cli/) | Flags, output formats (`table`/`json`/`csv`/`ndjson`), `providers` and `doctor` subcommands, exit codes |
| [Scheduling](https://hbmartin.github.io/omni-weather-forecast-apis/scheduling/) | Recurring collection with cron, launchd, or Task Scheduler |
| [Normalized Schema](https://hbmartin.github.io/omni-weather-forecast-apis/schema/) | Field/unit tables for every data point, the `WeatherCondition` enum, and typed error codes |
| [Observability](https://hbmartin.github.io/omni-weather-forecast-apis/observability/) | Metrics and log hooks, `MetricKind` events, and the OpenTelemetry bridge |
| [Database Design](https://hbmartin.github.io/omni-weather-forecast-apis/database/) | The SQLite schema, and the `stacking_features` view — aligned per-provider forecasts for the same point and valid time, already unit-normalized, which is the input a blending or verification model wants |
| [Extending](https://hbmartin.github.io/omni-weather-forecast-apis/extending/) | Response hooks, custom provider plugins, and quota trackers |
| [API Reference](https://hbmartin.github.io/omni-weather-forecast-apis/api-reference/) | Generated from the source |

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

The documentation site is built with [Zensical](https://zensical.org/)
(configured in `zensical.toml`) from the `docs/` directory:

```bash
uv sync --group docs
uv run zensical serve
```

## License

[Apache 2.0](LICENSE)

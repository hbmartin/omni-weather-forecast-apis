# omni-weather-forecast-apis

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)

Async Python library that fans out forecast requests across multiple weather providers and normalizes the results into one typed Pydantic schema. It preserves provider-native cadence and time boundaries while converting units and condition codes into a common representation.

## Features

- **Multi-provider fan-out** with async orchestration and partial-failure tolerance
- **Typed normalized schema** — common Pydantic models for minutely, hourly, daily, and alert data
- **Plugin architecture** — 13 providers with typed per-provider config validation
- **Rate limiting** — global concurrency and RPS limits with per-provider overrides
- **CLI** — loads a TOML config, queries providers, and persists normalized output to SQLite

## Supported Providers

| Provider | Plugin ID | API Key | Notes |
|----------|-----------|---------|-------|
| [Open-Meteo](https://open-meteo.com/) | `open_meteo` | Optional | Free tier; multiple forecast models |
| [MET Norway](https://api.met.no/) | `met_norway` | No | Requires `user_agent` identification |
| [NWS / NOAA](https://www.weather.gov/documentation/services-web-api) | `nws` | No | US coverage only; requires `user_agent` |
| [OpenWeather](https://openweathermap.org/api) | `openweather` | Yes | |
| [WeatherAPI](https://www.weatherapi.com/) | `weatherapi` | Yes | |
| [Tomorrow.io](https://www.tomorrow.io/) | `tomorrow_io` | Yes | |
| [Visual Crossing](https://www.visualcrossing.com/) | `visual_crossing` | Yes | |
| [Weatherbit](https://www.weatherbit.io/) | `weatherbit` | Yes | |
| [Meteosource](https://www.meteosource.com/) | `meteosource` | Yes | |
| [Pirate Weather](https://pirateweather.net/) | `pirate_weather` | Yes | Dark Sky-compatible API |
| [Stormglass](https://stormglass.io/) | `stormglass` | Yes | Hourly only; multi-model |
| [Weather Unlocked](https://developer.weatherunlocked.com/) | `weather_unlocked` | Yes | Requires `app_id` + `app_key` |
| Google Weather | `google_weather` | — | Placeholder; currently unavailable |

## Installation

```bash
uv sync
```

## Configuration

The client and CLI both use a TOML configuration file that matches `OmniWeatherConfig`.

```toml
default_timeout_ms = 10000

[rate_limiting]
max_in_flight = 10
max_requests_per_second = 20

[[providers]]
plugin_id = "open_meteo"
enabled = true
config = { models = ["best_match", "ecmwf_ifs025"] }

[[providers]]
plugin_id = "met_norway"
enabled = true
config = { user_agent = "MyApp/1.0 ops@example.com", variant = "complete" }

[[providers]]
plugin_id = "openweather"
enabled = true
config = { api_key = "ow-...", units = "metric" }
rate_limit_rps = 5
timeout_ms = 8000
```

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
                config={"user_agent": "MyApp/1.0 ops@example.com"},
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


asyncio.run(main())
```

## CLI Usage

```bash
uv run omni-weather \
  --config ./config.toml \
  --lat 34.2484 \
  --lon -117.1931 \
  --sqlite ./forecasts.sqlite
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--config PATH` | Yes | — | Path to TOML configuration file |
| `--lat FLOAT` | Yes | — | Latitude (-90 to 90) |
| `--lon FLOAT` | Yes | — | Longitude (-180 to 180) |
| `--sqlite PATH` | Yes | — | SQLite database output path |
| `--provider ID` | No | all enabled | Restrict to specific provider(s); repeatable |
| `--granularity GRAN` | No | hourly + daily | `minutely`, `hourly`, or `daily`; repeatable |
| `--language LANG` | No | `en` | Provider language preference |
| `--include-raw` | No | off | Persist raw provider payloads |
| `--timeout-ms MS` | No | config value | Override the default timeout; provider-specific timeouts still take precedence |

**Exit codes:** `0` all providers succeeded, `1` at least one provider failed, `2` invalid arguments or configuration/load error.

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

## Development

```bash
# Lint and type-check
uv run black src
uv run ruff check src --fix
uv run pyrefly check src
uv run ty check src

# Complexity and tests
uv run lizard -Eduplicate src
uv run pytest tests/
```

## License

[Apache 2.0](LICENSE)

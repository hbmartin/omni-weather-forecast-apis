# omni-weather-forecast-apis

[![PyPI](https://img.shields.io/pypi/v/omni-weather-forecast-apis.svg)](https://pypi.org/project/omni-weather-forecast-apis/)
[![CI](https://github.com/hbmartin/omni-weather-forecast-apis/actions/workflows/ci.yml/badge.svg)](https://github.com/hbmartin/omni-weather-forecast-apis/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with pyrefly](https://img.shields.io/badge/🪲-pyrefly-fe8801.svg)](https://pyrefly.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/hbmartin/omni-weather-forecast-apis)

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

## Quick Start

```bash
# 1. Install
uv sync

# 2. Create a minimal config (Open-Meteo and MET Norway require no API keys)
cat > config.toml << 'EOF'
[[providers]]
plugin_id = "open_meteo"
config = { models = ["best_match"] }

[[providers]]
plugin_id = "met_norway"
config = { user_agent = "MyApp/1.0 ops@example.com" }
EOF

# 3. Run a forecast
uv run omni-weather \
  --config ./config.toml \
  --lat 40.7128 \
  --lon -74.0060 \
  --sqlite ./forecasts.sqlite
```

## Installation

```bash
uv sync
```

## How It Works

1. **Fan-out** — A `ForecastRequest` is dispatched concurrently to every enabled provider using async tasks, bounded by configurable concurrency and rate limits.
2. **Normalize** — Each provider plugin converts its native response into the common `SourceForecast` schema, translating units (e.g. Fahrenheit to Celsius, mph to m/s) and mapping provider-specific condition codes to a shared `WeatherCondition` enum.
3. **Aggregate** — Results are collected into a single `ForecastResponse`. Providers that succeed return `ProviderSuccess` with their forecasts; providers that fail return `ProviderError` with a typed error code. The response always completes, even if some providers fail.

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

```bash
uv run omni-weather \
  --config ./config.toml \
  --lat 34.2484 \
  --lon -117.1931 \
  --sqlite ./forecasts.sqlite

# Query only specific providers
uv run omni-weather \
  --config ./config.toml \
  --lat 34.2484 \
  --lon -117.1931 \
  --sqlite ./forecasts.sqlite \
  --provider open_meteo \
  --provider nws \
  --granularity hourly
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

## Partial Failures

The library is designed for partial-failure tolerance. When some providers fail (network errors, rate limits, auth issues), the response still completes with results from the providers that succeeded.

Each entry in `response.results` is either a `ProviderSuccess` or `ProviderError`, distinguished by the `status` field. The `response.summary` provides counts at a glance:

```python
response.summary
# ForecastResponseSummary(total=3, succeeded=2, failed=1)
```

`ProviderError` includes a typed `error.code` (`AUTH_FAILED`, `RATE_LIMITED`, `TIMEOUT`, `NETWORK`, `PARSE`, `NOT_AVAILABLE`, `UNKNOWN`), a human-readable `error.message`, the `error.http_status` when available, and `error.latency_ms` for how long the request ran before failing.

The CLI reflects this in exit codes: `0` means all providers succeeded, `1` means at least one failed (but partial results are still written to SQLite).

## Normalized Schema

All provider responses are normalized into a common set of Pydantic models. Units are standardized: temperatures in °C, wind speeds in m/s, pressure in hPa, precipitation in mm, visibility in km.

### `WeatherDataPoint` (hourly)

| Field | Type | Unit |
|-------|------|------|
| `temperature`, `apparent_temperature`, `dew_point` | float \| None | °C |
| `humidity` | float \| None | % (0-100) |
| `wind_speed`, `wind_gust` | float \| None | m/s |
| `wind_direction` | float \| None | degrees |
| `pressure_sea`, `pressure_surface` | float \| None | hPa |
| `precipitation`, `rain`, `snow`, `snow_depth` | float \| None | mm |
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
| `precipitation_sum`, `rain_sum`, `snowfall_sum` | float \| None | mm |
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
| `google_weather` | `api_key`? (placeholder, currently unavailable) |

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

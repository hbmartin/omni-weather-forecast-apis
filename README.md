# omni-weather-forecast-apis

`omni-weather-forecast-apis` is an async Python library that fans out forecast requests across multiple providers and normalizes the results into one typed schema. It preserves provider-native cadence and time boundaries while converting units and condition codes into a common representation.

## Features

- Async orchestrator with partial-failure tolerance.
- Common Pydantic schema for minutely, hourly, daily, and alert data.
- Provider plugin architecture with typed config validation.
- Global concurrency and request-per-second limiting plus per-provider overrides.
- CLI that loads a TOML config, requires `--lat` and `--lon`, and persists normalized output to SQLite.

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

The CLI requires a config file plus `--lat` and `--lon`, and writes normalized results into SQLite.

```bash
uv run omni-weather \
  --config ./config.toml \
  --lat 34.2484 \
  --lon -117.1931 \
  --sqlite ./forecasts.sqlite
```

Optional flags:

- `--provider <slug>`: limit the run to one or more configured providers.
- `--granularity hourly --granularity daily`: request specific granularities.
- `--language en`: provider language preference.
- `--include-raw`: persist raw provider payloads.
- `--timeout-ms 15000`: override the request timeout.

## SQLite Output

The CLI creates a normalized database with these tables:

- `forecast_runs`
- `provider_results`
- `source_forecasts`
- `minutely_points`
- `hourly_points`
- `daily_points`
- `alerts`

Each run stores the request metadata, one row per provider result, one row per model/source forecast, and time-series rows for each granularity.

## Supported Providers

- `openweather`
- `open_meteo`
- `nws`
- `weatherapi`
- `tomorrow_io`
- `visual_crossing`
- `weatherbit`
- `meteosource`
- `pirate_weather`
- `met_norway`
- `google_weather`
- `stormglass`
- `weather_unlocked`

## Development

The repository instructions require these commands after changes:

```bash
uv run black src
uv run ruff check src --fix
uv run pyrefly check src
uv run ty check src
uv run lizard -Eduplicate src
uv run pytest tests/
```

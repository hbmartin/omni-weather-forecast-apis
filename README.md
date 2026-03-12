# omni-weather-forecast-apis

Universal Weather Forecast Aggregation Library for Python.

A unified interface to 13+ weather forecast APIs, normalizing heterogeneous response formats into a common, type-safe Pydantic schema.

## Features

- **13 provider plugins**: OpenWeather, Open-Meteo, NWS, WeatherAPI, Tomorrow.io, Visual Crossing, Weatherbit, Meteosource, Pirate Weather, MET Norway, Google Weather, Stormglass, Weather Unlocked
- **Type-safe common schema**: Pydantic-validated normalized output with SI units
- **Partial failure tolerance**: If some providers fail, results from successful ones are still returned
- **Concurrent fetching**: Async fan-out with configurable rate limiting
- **Multi-model support**: Open-Meteo and Stormglass return per-model forecasts
- **CLI with SQLite output**: Fetch forecasts and save to a normalized database
- **Plugin architecture**: Register custom provider plugins

## Installation

```bash
pip install omni-weather-forecast-apis
```

## Quick Start

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
                plugin_id=ProviderId.OPENWEATHER,
                config={"api_key": "your-api-key"},
            ),
        ],
    )

    async with await create_omni_weather(config) as client:
        response = await client.forecast(
            ForecastRequest(
                latitude=34.2484,
                longitude=-117.1931,
                granularity=[Granularity.HOURLY, Granularity.DAILY],
            )
        )

        print(f"{response.summary.succeeded}/{response.summary.total} providers succeeded")

        for result in response.results:
            if result.status == "success":
                for forecast in result.forecasts:
                    print(
                        f"  [{forecast.source.provider.value}/{forecast.source.model}]"
                        f" {len(forecast.hourly)} hourly,"
                        f" {len(forecast.daily)} daily points"
                    )
            else:
                print(
                    f"  [{result.provider.value}] FAILED:"
                    f" {result.error.code.value} - {result.error.message}"
                )


asyncio.run(main())
```

## CLI Usage

Create a JSON config file:

```json
{
  "providers": [
    {
      "plugin_id": "open_meteo",
      "config": {}
    },
    {
      "plugin_id": "openweather",
      "config": {"api_key": "your-key"}
    }
  ],
  "default_timeout_ms": 10000
}
```

Run the CLI:

```bash
omni-weather --config config.json --lat 34.2484 --lon -117.1931
```

### CLI Flags

| Flag | Required | Description |
|------|----------|-------------|
| `--config` | Yes | Path to JSON configuration file |
| `--lat` | Yes | Latitude in decimal degrees |
| `--lon` | Yes | Longitude in decimal degrees |
| `--granularity` | No | Granularities to request: `minutely`, `hourly`, `daily` (default: `hourly daily`) |
| `--output` | No | Path to SQLite database for saving results |
| `--include-raw` | No | Include raw API responses in output |
| `--timeout` | No | Timeout per provider in milliseconds (default: 10000) |
| `--providers` | No | Only fetch from these providers (space-separated IDs) |

## Provider Configuration

Each provider requires specific configuration. Providers that don't require API keys (Open-Meteo, NWS, MET Norway) can be used with minimal config.

### Provider IDs

`openweather`, `open_meteo`, `nws`, `weatherapi`, `tomorrow_io`, `visual_crossing`, `weatherbit`, `meteosource`, `pirate_weather`, `met_norway`, `google_weather`, `stormglass`, `weather_unlocked`

## Unit Conventions

All values use SI units internally:

| Measurement | Unit |
|-------------|------|
| Temperature | °C |
| Wind speed | m/s |
| Pressure | hPa |
| Precipitation | mm |
| Visibility | km |
| Wind direction | degrees |
| Humidity | % (0-100) |
| Cloud cover | % (0-100) |
| Probability | 0-1 |

## License

Apache-2.0

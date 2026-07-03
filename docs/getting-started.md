# Getting Started

## Install

```bash
uv sync
```

Requires Python 3.14+.

## Minimal CLI run

Open-Meteo and MET Norway require no API keys, so this works out of the box:

```bash
cat > config.toml << 'EOF'
[[providers]]
plugin_id = "open_meteo"
config = { models = ["best_match"] }

[[providers]]
plugin_id = "met_norway"
config = { user_agent = "MyApp/1.0 ops@example.com" }
EOF

uv run omni-weather \
  --config ./config.toml \
  --lat 40.7128 \
  --lon -74.0060 \
  --sqlite ./forecasts.sqlite
```

Add `--format json` to emit the full normalized response as JSON on stdout,
or omit `--sqlite` to skip persistence entirely.

## Library usage

```python
import asyncio

from omni_weather_forecast_apis.client import create_omni_weather
from omni_weather_forecast_apis.types import (
    ForecastRequest,
    OmniWeatherConfig,
    ProviderId,
    ProviderRegistration,
)


async def main() -> None:
    config = OmniWeatherConfig(
        providers=[
            ProviderRegistration(
                plugin_id=ProviderId.OPEN_METEO,
                config={"models": ["best_match"]},
            ),
        ],
    )
    async with await create_omni_weather(config) as client:
        response = await client.forecast(
            ForecastRequest(latitude=40.7128, longitude=-74.0060),
        )
    for result in response.results:
        print(result.provider.value, result.status)


asyncio.run(main())
```

## Keeping API keys out of config files

Reference environment variables from any provider `config` value:

```toml
[[providers]]
plugin_id = "openweather"
config = { api_key = "${OPENWEATHER_API_KEY}" }
```

See [Configuration](configuration.md#environment-variable-placeholders) for details.

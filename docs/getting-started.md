# Getting Started

## Install

```bash
uv sync --extra cli
```

Requires Python 3.13+.

## Interactive CLI setup

```bash
uv run omni-weather init
```

The wizard asks for required coordinates, providers, provider credentials,
SQLite output, and forecast granularities. Open-Meteo is the recommended
keyless default. MET Norway and NWS share one application/contact identity;
the other providers are grouped as requiring API keys. The wizard validates
the generated TOML and provider settings, shows an exact preview, asks before
writing or overwriting, and offers a test forecast (default: yes).

Credential input is masked, but credentials are deliberately written directly
to the config and visible in the preview. The generated config is owner-only
on POSIX. Use environment placeholders in a manually maintained config when
you do not want secrets stored there.

Running `uv run omni-weather` without `--config` uses the platform-native
config, falls back to the legacy `~/.config/omni_weather_forecast_apis.toml`,
and starts this wizard if neither exists. Automatic setup only runs in an
interactive terminal; after setup it executes the original forecast command.

## Manual minimal CLI run

Open-Meteo and MET Norway require no API keys, so this works out of the box:

```bash
cat > config.toml << 'EOF'
[[providers]]
plugin_id = "open_meteo"
config = { models = ["best_match"] }

[[providers]]
plugin_id = "met_norway"
config = { user_agent = "MyApp/1.0 you@yourdomain.com" }
EOF

uv run omni-weather \
  --config ./config.toml \
  --lat 40.7128 \
  --lon -74.0060 \
  --sqlite ./forecasts.sqlite
```

Add `--format json` to emit the full normalized response as JSON on stdout,
or omit `--sqlite` to skip persistence entirely.

Use `uv run omni-weather providers` to compare provider requirements and
official signup links. Use `uv run omni-weather doctor` for static aggregated
diagnostics. `doctor --live` opts into real provider calls, which can consume
quota; add repeatable `--provider ID` filters to narrow those checks.

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

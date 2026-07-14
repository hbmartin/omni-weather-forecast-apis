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
                timezone="America/Los_Angeles",
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

`ForecastRequest.timezone` is an optional, validated IANA name. Library callers
should provide it when available. A provider-supplied IANA timezone takes
precedence; otherwise plugins that need civil-time conversion use the request
value, then fall back to an uncached Open-Meteo coordinate lookup. A lookup
failure becomes an error for only that provider, so other provider requests can
still succeed.

Example output:

```
ProviderId.OPEN_METEO 2026-03-13 18:00:00+00:00: 12.3°C, WeatherCondition.PARTLY_CLOUDY
ProviderId.OPEN_METEO 2026-03-13 19:00:00+00:00: 11.8°C, WeatherCondition.OVERCAST
ProviderId.MET_NORWAY 2026-03-13 18:00:00+00:00: 12.1°C, WeatherCondition.RAIN
...
```

The response always completes even when some providers fail — see [Normalized
Schema](schema.md#responses-and-errors) for the typed error codes, and
[Observability](observability.md) for metrics hooks.

## Keeping API keys out of config files

Reference environment variables from any provider `config` value:

```toml
[[providers]]
plugin_id = "openweather"
config = { api_key = "${OPENWEATHER_API_KEY}" }
```

See [Configuration](configuration.md#environment-variable-placeholders) for details.

# CLI

Install the CLI extra:

```bash
pip install "omni-weather-forecast-apis[cli]"
```

The base package still installs the `omni-weather` wrapper because Python
extras cannot conditionally install console scripts. If the CLI dependencies
are absent, it exits `2` with an installation hint.

## Interactive setup

```bash
omni-weather init [--config PATH]
```

The wizard writes all interaction to stderr and prompts in this order:

1. Required latitude and longitude.
2. At least one provider. Open-Meteo is the recommended, preselected keyless
   provider; MET Norway and NWS are also keyless, and the other ten are grouped
   under “Requires API key.”
3. One shared application name/contact email when MET Norway or NWS is used.
4. Masked credentials for keyed providers. Weather Unlocked collects both an
   application ID and application key.
5. A required SQLite path, defaulting to the platform data directory.
6. One or more compatible granularities, defaulting to hourly and daily.
7. Optional automatic daily collection at a chosen local time, using cron on
   Linux, launchd on macOS, or Windows Task Scheduler.

Generated TOML and every provider setting are validated before an exact preview
is displayed. The preview contains collected credentials. Nothing is created
or overwritten until the final confirmation. Writes are atomic; new
directories and the config receive private POSIX permissions. Explicit `init`
then offers a platform-native daily schedule, defaulting to no, followed by a
test forecast, defaulting to yes. Re-running `init` for the same config replaces
that config's managed schedule rather than adding a duplicate.

With no explicit `--config`, forecasts use the platform-native
`omni-weather/config.toml`, then the legacy
`~/.config/omni_weather_forecast_apis.toml`. If neither exists and stdin/stderr
are interactive, the wizard runs automatically and the original forecast
continues with its overrides. Non-interactive first use exits `2` with setup
instructions. An explicitly supplied missing file is always an error.

## Forecast

```bash
uv run omni-weather --config ./config.toml --lat 40.7128 --lon -74.0060
```

Each invocation performs exactly one forecast collection. For recurring
collection, see [Scheduling](scheduling.md).

`--provider` and `--granularity` are repeatable, and narrow the run without
editing the config:

```bash
uv run omni-weather \
  --config ./config.toml \
  --lat 34.2484 \
  --lon -117.1931 \
  --sqlite ./forecasts.sqlite \
  --provider open_meteo \
  --provider nws \
  --granularity hourly
```

## Flags

| Flag | Description |
|------|-------------|
| `--config PATH` | TOML config path (default: platform path, then legacy path) |
| `--lat` / `--lon` | Coordinates in decimal degrees (override config) |
| `--sqlite PATH` | SQLite output file (overrides config); persistence is skipped when neither is set |
| `--format {table,json,csv,ndjson}` | Output format (default: `table`) |
| `--provider ID` | Restrict to one or more configured providers (repeatable) |
| `--granularity {minutely,hourly,daily}` | Granularity to request (repeatable) |
| `--language CODE` | Provider language preference |
| `--include-raw` | Persist raw provider payloads alongside normalized results |
| `--no-raw-archive` | Skip the [raw HTTP payload archive](configuration.md#raw-payload-archive) (`raw/<UTC timestamp>-<unique suffix>.jsonl.gz` next to the SQLite database), which is written by default |
| `--timeout-ms N` | Override the default request timeout |
| `--debug` | Verbose logging to stderr and a log file next to the SQLite database, or `./omni-weather.log` when `--sqlite` is omitted |

The forecast exit code is `0` when every provider succeeded, `1` when at least
one provider failed, and `2` for invalid arguments or configuration/load
errors. Partial provider failures are visible to schedulers and shell scripts.

When SQLite output is configured, the CLI caches coordinate-to-IANA-timezone
mappings in a companion file beside the forecast database. For example,
`forecasts.sqlite` uses `forecasts.timezones.sqlite`. Coordinates are keyed at
four decimal places and entries do not expire. Missing, locked, corrupt, or
unwritable cache state produces a warning and collection continues uncached;
the cache is an optimization, not a prerequisite for other providers.

## Provider discovery

```bash
omni-weather providers
```

This renders one catalog shared with the setup wizard, including provider ID
and name, coverage, supported granularities, authentication requirements, and
official signup/setup links.

## Diagnostics

```bash
omni-weather doctor [--config PATH] [--provider ID]... [--live]
```

Static doctor checks aggregate config presence, TOML and Pydantic validation,
required coordinates, typed provider settings, recursive environment
references, config/SQLite path type and writability, POSIX config permissions,
duplicate registrations, provider/granularity compatibility, and the
platform-native daily schedule. A missing or inactive schedule is a warning,
not a failure. Environment variable names and presence are shown; values are
never printed.

Repeatable `--provider` filters narrow provider-specific static and live checks;
top-level config and path checks always run. Static mode never contacts a
weather API. `--live` checks all enabled providers (or the selected filters),
skips statically invalid providers, and does not persist results. These calls
can consume provider quota, trigger rate limits, or incur provider charges.

Doctor exits `0` when required checks pass, including when there are warnings
only, and `1` for any static or live failure. Exit `2` is reserved for invalid
invocation or unexpected operational errors. Cancelling explicit `init` exits
`0`; cancelling automatic setup exits `2`. Ctrl+C exits `130` with a concise
`Aborted.` message rather than a traceback.

## Output formats

`--format table` (default) renders a per-provider summary table: status,
latency, row counts per granularity, and error details for failures.

`--format json` prints the entire normalized `ForecastResponse` as JSON on
stdout — ideal for piping into `jq` or another program:

```bash
uv run omni-weather --config config.toml --lat 40.7 --lon -74.0 --format json \
  | jq '.results[] | {provider, status}'
```

`--format csv` and `--format ndjson` emit one row/line per forecast data
point, flattened for data tooling (pandas, DuckDB, `jq`). Every row starts
with `provider`, `model`, `granularity` (`minutely` / `hourly` / `daily`), and
the source `timezone`, followed by the normalized point fields; fields that
don't apply to a row's granularity are empty.

- **csv** — a single wide table with a fixed column order derived from the
  normalized schema. Weather alerts are omitted (a note is printed to
  stderr) and provider errors are summarized on stderr, so stdout stays
  machine-parseable.
- **ndjson** — one compact JSON object per line, each tagged with a `type`
  of `forecast_point`, `alert`, or `provider_error`:

```bash
uv run omni-weather --config config.toml --lat 40.7 --lon -74.0 --format ndjson \
  | jq 'select(.type == "forecast_point") | {provider, timestamp, temperature}'
```

## SQLite output

When `--sqlite` (or `sqlite` in the config) is set, the CLI creates a
normalized database with these tables:

| Table | Contents |
|-------|----------|
| `forecast_runs` | Request metadata per invocation |
| `provider_results` | One row per provider outcome (success or error) |
| `source_forecasts` | One row per model/source forecast within a provider |
| `minutely_points` | Precipitation intensity at minute intervals |
| `hourly_points` | Normalized hourly forecast rows |
| `daily_points` | Normalized daily summary rows |
| `alerts` | Weather alerts and warnings |
| `provider_logs` | Per-provider lifecycle log entries per run |
| `provider_quota_usage` | Requests per provider per UTC day (daily quota enforcement) |

`source_forecasts.timezone` records the IANA timezone actually used for a
source's civil-time normalization. The companion timezone cache is intentionally
separate from this normalized forecast database.

The `stacking_features` view joins hourly points with their provider, model,
run cycle, and forecast horizon — a ready-made feature matrix for
downstream ensemble/ML work. See [Database Design](database.md) for the
complete relationship model, column reference, indexes, lifecycle, and query
examples, and [Extending](extending.md) for downstream integration patterns.

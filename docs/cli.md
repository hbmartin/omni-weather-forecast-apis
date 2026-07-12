# CLI

```bash
uv run omni-weather --config ./config.toml --lat 40.7128 --lon -74.0060
```

## Flags

| Flag | Description |
|------|-------------|
| `--config PATH` | TOML config path (default: `~/.config/omni_weather_forecast_apis.toml`) |
| `--lat` / `--lon` | Coordinates in decimal degrees (override config) |
| `--sqlite PATH` | SQLite output file (overrides config); persistence is skipped when neither is set |
| `--format {table,json,csv,ndjson}` | Output format (default: `table`) |
| `--provider ID` | Restrict to one or more configured providers (repeatable) |
| `--granularity {minutely,hourly,daily}` | Granularity to request (repeatable) |
| `--language CODE` | Provider language preference |
| `--include-raw` | Persist raw provider payloads alongside normalized results |
| `--timeout-ms N` | Override the default request timeout |
| `--debug` | Verbose logging to stderr and a log file next to the SQLite database, or `./omni-weather.log` when `--sqlite` is omitted |

The exit code is `0` when every provider succeeded, `1` when at least one
provider failed, and `2` for invalid arguments or configuration/load errors.
Partial provider failures are visible to schedulers and shell scripts.

Rich tables and loguru debug logging require the `cli` extra
(`pip install "omni-weather-forecast-apis[cli]"`). Without it the CLI
degrades gracefully: tables render as plain text and `--debug` uses
stdlib logging.

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
with `provider`, `model`, and `granularity` (`minutely` / `hourly` /
`daily`), followed by the normalized point fields; fields that don't apply
to a row's granularity are empty.

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

The `stacking_features` view joins hourly points with their provider, model,
run cycle, and forecast horizon — a ready-made feature matrix for
downstream ensemble/ML work (see [Extending](extending.md)).

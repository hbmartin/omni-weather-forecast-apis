# Configuration

The client and CLI both use a TOML configuration file that matches
`OmniWeatherConfig`.

When the CLI has no explicit `--config`, it first checks
`platformdirs.user_config_path("omni-weather", appauthor=False) / "config.toml"`,
then the legacy
`~/.config/omni_weather_forecast_apis.toml`. If neither exists, an interactive
terminal starts `omni-weather init`; non-interactive use exits `2` with setup
instructions. An explicitly supplied missing file never launches the wizard.

The platform defaults, with XDG and other platform overrides still honored,
are:

| Platform | Configuration | SQLite data |
|----------|---------------|-------------|
| Linux | `~/.config/omni-weather/config.toml` | `~/.local/share/omni-weather/forecasts.sqlite` |
| macOS | `~/Library/Application Support/omni-weather/config.toml` | `~/Library/Application Support/omni-weather/forecasts.sqlite` |
| Windows | `%LOCALAPPDATA%\omni-weather\config.toml` | `%LOCALAPPDATA%\omni-weather\forecasts.sqlite` |

```toml
latitude = 40.7128
longitude = -74.0060
sqlite = "forecasts.sqlite"
granularity = ["hourly", "daily"]
language = "en"
include_raw = false
debug = false
default_timeout_ms = 10000

[rate_limiting]
max_in_flight = 10
max_requests_per_second = 20

[retry]
max_attempts = 3
initial_backoff_ms = 500
max_backoff_ms = 8000
backoff_multiplier = 2.0
jitter = true

[http]
max_connections = 20
max_keepalive_connections = 10
connect_timeout_ms = 5000
cache_enabled = true
cache_max_entries = 256
raw_archive_enabled = true

[[providers]]
plugin_id = "open_meteo"
enabled = true
config = { models = ["best_match", "ecmwf_ifs025"] }

[[providers]]
plugin_id = "openweather"
config = { api_key = "${OPENWEATHER_API_KEY}" }
rate_limit_rps = 1.0
timeout_ms = 8000
max_requests_per_day = 900
```

## Top-level options

| Key | Default | Description |
|-----|---------|-------------|
| `providers` | — | List of provider registrations (required) |
| `latitude` / `longitude` | `None` | Default coordinates for the CLI |
| `sqlite` | `None` | Default SQLite output path for the CLI; persistence is skipped when unset |
| `granularity` | `["hourly", "daily"]` | Granularities to request |
| `language` | `"en"` | Provider language preference |
| `include_raw` | `false` | Persist raw provider payloads |
| `default_timeout_ms` | `10000` | Per-provider fetch timeout |
| `debug` | `false` | Verbose CLI logging |

## Retry policy — `[retry]`

Transient failures — network errors, timeouts, and HTTP 429 rate limits —
are retried with exponential backoff and jitter. A server-provided
`Retry-After` header is honored; retries are abandoned when it exceeds 60
seconds. Non-transient failures such as auth errors are never retried.

| Key | Default | Description |
|-----|---------|-------------|
| `max_attempts` | `3` | Total attempts per provider fetch (1 disables retries) |
| `initial_backoff_ms` | `500` | Delay before the first retry |
| `max_backoff_ms` | `8000` | Backoff ceiling |
| `backoff_multiplier` | `2.0` | Exponential growth factor |
| `jitter` | `true` | Randomize each delay to avoid thundering herds |

Setting only one of `initial_backoff_ms` / `max_backoff_ms` adjusts the
other's default to keep `initial <= max`; setting both to conflicting
values is a validation error.

A per-provider `retry` table on a registration overrides the global policy.

## HTTP client — `[http]`

| Key | Default | Description |
|-----|---------|-------------|
| `max_connections` | `20` | Connection pool cap |
| `max_keepalive_connections` | `10` | Idle keep-alive connections |
| `connect_timeout_ms` | `5000` | TCP/TLS connect timeout |
| `cache_enabled` | `true` | Conditional-request response cache |
| `cache_max_entries` | `256` | In-memory cache size |
| `raw_archive_enabled` | `true` | Archive raw HTTP payloads next to the SQLite database |

Setting only one of `max_connections` / `max_keepalive_connections` adjusts
the other's default to keep `keepalive <= connections`; setting both to
conflicting values is a validation error.

The cache is standards-aware: responses with `Cache-Control: max-age` or
`Expires` are served from memory while fresh, and stale responses carrying
`ETag`/`Last-Modified` validators are revalidated with conditional requests
and reused on `304 Not Modified`. Responses that declare `Vary` are only
reused for requests sending the same values for the named headers, and
`Vary: *` responses are never cached. MET Norway's terms of service require
this behavior and the NWS strongly encourages it. Requests carrying
`Authorization` or `Cookie` headers bypass the shared cache.

### Raw payload archive

When persisting to SQLite, every network response is additionally archived as
gzipped JSONL — one line per response, carrying the timestamp, method, URL,
status, and body — into a `raw/` directory next to the database. Each
invocation writes one file, linked from `forecast_runs.raw_archive_path` (see
[Database Design](database.md#forecast_runs)). The archive preserves response
bodies for future parser investigation and replay. It only covers requests
recorded after archiving is enabled, so it cannot reconstruct older
normalized-only runs.

URLs are stored verbatim, **including API keys in query strings**, so keep
archives out of version control — this repository ignores `raw/`. Files
accumulate until deleted manually. Disable with `raw_archive_enabled = false`
here, or `--no-raw-archive` for a single run.

### Location-timezone cache

When the CLI persists forecasts to SQLite, it keeps coordinate-to-IANA-zone
resolutions in a separate companion database (`forecasts.timezones.sqlite`).
Keys retain six decimal places. Each entry records its source, resolver
version, and resolution timestamp; entries older than 30 days or from an older
resolver version are refreshed. Lookup misses use the aggregation client's
configured connection pool, HTTP cache, metrics hooks, and raw-response
recorder. Cache failures produce warnings and do not prevent providers that
can determine their own timezone from running.

## Provider registrations — `[[providers]]`

| Key | Default | Description |
|-----|---------|-------------|
| `plugin_id` | — | Provider slug (see [Providers](providers.md)) |
| `config` | — | Provider-specific config dict |
| `enabled` | `true` | Toggle without deleting the block |
| `rate_limit_rps` | `None` | Per-provider requests-per-second cap |
| `timeout_ms` | `None` | Per-provider timeout override |
| `max_requests_per_day` | `None` | Daily quota cap (see below) |
| `retry` | `None` | Per-provider retry policy override |

## Daily quotas

Most free tiers are capped per day, not per second. Set
`max_requests_per_day` on a registration and the client refuses to fetch
once the day's budget (UTC) is spent, returning a `quota_exceeded` error
for that provider instead of burning the quota:

```toml
[[providers]]
plugin_id = "openweather"
config = { api_key = "${OPENWEATHER_API_KEY}" }
max_requests_per_day = 900
```

Each fetch attempt (including retries) counts one request. The CLI persists
counts in the SQLite database (`provider_quota_usage` table) so limits
survive across runs; library users can pass any
`omni_weather_forecast_apis.quota.QuotaTracker` implementation with atomic
`try_consume` support to the client (`InMemoryQuotaTracker` is the default,
`SqliteQuotaTracker` is bundled).

## Environment variable placeholders

Any string value inside a provider `config` block can reference an
environment variable instead of embedding a secret:

```toml
# whole-string reference
config = { api_key = "${OPENWEATHER_API_KEY}" }

# explicit marker table (equivalent)
config = { api_key = { env = "OPENWEATHER_API_KEY" } }
```

Resolution happens when the client initializes and recurses through nested
tables and arrays. A placeholder naming an unset variable turns into a
per-provider initialization error; other providers are unaffected. Partial
interpolation (`"prefix-${VAR}"`) is intentionally not supported — only
whole-string placeholders are resolved.

`omni-weather init` instead collects credential values with masked prompts and
stores them directly in TOML. Its exact preview includes those values by
design. Confirm only in a private terminal and protect the generated file; the
wizard writes it atomically with mode `0600` and creates new config/data
directories privately on POSIX. `omni-weather doctor` reports missing
environment references by name without printing their resolved values.
